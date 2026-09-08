"""Newton commit/rollback orchestration for the stateful 2D fiber frame."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
import math
from time import perf_counter_ns
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DAssembly,
    StatefulFiberFrame2DProblem,
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.materials.trial_runtime import MaterialTrialRuntimeRecorder
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    SOLVE_FREE_EQUATIONS_DISPOSITION,
    VECTOR_INCREMENT_TIMING_SCOPE,
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
    VectorIncrementRuntimeRecorder,
    newton_raphson_vector,
)


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _normalize_initial_free_coordinates_m(
    problem: StatefulFiberFrame2DProblem,
    values: Sequence[float] | np.ndarray,
    *,
    name: str = "initial_free_coordinates_m",
) -> tuple[float, ...]:
    try:
        normalized = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite vector") from exc
    expected_shape = (len(problem.free_global_dofs),)
    if normalized.shape != expected_shape:
        raise ValueError(
            f"{name} must have shape {expected_shape}, got {normalized.shape}"
        )
    if not np.all(np.isfinite(normalized)):
        raise ValueError(f"{name} must contain only finite values")
    return tuple(float(value) for value in normalized)


@dataclass
class _StatefulFiberFrame2DNewtonRuntimeRecorder:
    """Caller-local Newton timing observed at the stateful adapter boundary."""

    clock_ns: Callable[[], int] = field(repr=False, compare=False)
    total_wall_ns: int = field(default=0, init=False)
    assemble_wall_ns: int = field(default=0, init=False)
    run_count: int = field(default=0, init=False)
    completed_run_count: int = field(default=0, init=False)
    exception_run_count: int = field(default=0, init=False)
    assemble_call_count: int = field(default=0, init=False)
    assemble_exception_count: int = field(default=0, init=False)
    increment: VectorIncrementRuntimeRecorder = field(init=False, repr=False)
    material: MaterialTrialRuntimeRecorder = field(init=False, repr=False)
    _active: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.increment = VectorIncrementRuntimeRecorder(clock_ns=self.clock_ns)
        self.material = MaterialTrialRuntimeRecorder(clock_ns=self.clock_ns)

    @property
    def unattributed_wall_ns(self) -> int:
        return self.total_wall_ns - self.assemble_wall_ns - self.increment.wall_ns

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_wall_ns": self.total_wall_ns,
            "assemble_wall_ns": self.assemble_wall_ns,
            "material_trial": self.material.to_dict(),
            "linear_solve_wall_ns": self.increment.wall_ns,
            "linear_solve_reason": "measured_increment_backend",
            "linear_solve_scope": VECTOR_INCREMENT_TIMING_SCOPE,
            "unattributed_wall_ns": self.unattributed_wall_ns,
            "run_count": self.run_count,
            "completed_run_count": self.completed_run_count,
            "exception_run_count": self.exception_run_count,
            "assemble_call_count": self.assemble_call_count,
            "assemble_exception_count": self.assemble_exception_count,
            "linear_solve_call_count": self.increment.call_count,
            "linear_solve_exception_count": self.increment.exception_count,
            "active": self._active,
        }

    def _read_clock(self) -> int:
        value = self.clock_ns()
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("clock_ns must return an integer nanosecond value")
        return value

    def _elapsed(self, started_ns: int) -> int:
        finished_ns = self._read_clock()
        if finished_ns < started_ns:
            raise ValueError("clock_ns must be monotonic")
        return finished_ns - started_ns

    def _begin_run(self) -> int:
        if self._active:
            raise ValueError("runtime recorder is already active")
        started_ns = self._read_clock()
        self._active = True
        self.run_count += 1
        return started_ns

    def _finish_run(self, started_ns: int, *, raised: bool) -> None:
        try:
            self.total_wall_ns += self._elapsed(started_ns)
            if raised:
                self.exception_run_count += 1
            else:
                self.completed_run_count += 1
        finally:
            self._active = False

    def _begin_assemble(self) -> int:
        if not self._active:
            raise ValueError("runtime recorder has no active Newton solve")
        return self._read_clock()

    def _finish_assemble(self, started_ns: int, *, raised: bool) -> None:
        self.assemble_wall_ns += self._elapsed(started_ns)
        self.assemble_call_count += 1
        if raised:
            self.assemble_exception_count += 1


@dataclass
class StatefulFiberFrame2DLoadStepRuntimeRecorder:
    """Volatile timing for one or more stateful load-step solve attempts.

    The recorder is caller-owned and never enters a numerical result, checkpoint,
    or canonical hash. Newton assembly is timed at this solver adapter boundary;
    increment timing includes backend matrix preparation and sparse diagnostics,
    rather than claiming isolated linear algebra kernel time.
    """

    clock_ns: Callable[[], int] = field(
        default=perf_counter_ns,
        repr=False,
        compare=False,
    )
    total_wall_ns: int = field(default=0, init=False)
    terminal_trial_assembly_wall_ns: int = field(default=0, init=False)
    run_count: int = field(default=0, init=False)
    completed_run_count: int = field(default=0, init=False)
    exception_run_count: int = field(default=0, init=False)
    terminal_trial_assembly_call_count: int = field(default=0, init=False)
    terminal_trial_assembly_exception_count: int = field(default=0, init=False)
    newton: _StatefulFiberFrame2DNewtonRuntimeRecorder = field(
        init=False,
        repr=False,
    )
    terminal_material: MaterialTrialRuntimeRecorder = field(init=False, repr=False)
    _active: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not callable(self.clock_ns):
            raise ValueError("clock_ns must be callable")
        self.newton = _StatefulFiberFrame2DNewtonRuntimeRecorder(clock_ns=self.clock_ns)
        self.terminal_material = MaterialTrialRuntimeRecorder(clock_ns=self.clock_ns)

    @property
    def unattributed_wall_ns(self) -> int:
        return (
            self.total_wall_ns
            - self.newton.total_wall_ns
            - self.terminal_trial_assembly_wall_ns
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_wall_ns": self.total_wall_ns,
            "terminal_trial_assembly_wall_ns": (self.terminal_trial_assembly_wall_ns),
            "unattributed_wall_ns": self.unattributed_wall_ns,
            "run_count": self.run_count,
            "completed_run_count": self.completed_run_count,
            "exception_run_count": self.exception_run_count,
            "terminal_trial_assembly_call_count": (
                self.terminal_trial_assembly_call_count
            ),
            "terminal_trial_assembly_exception_count": (
                self.terminal_trial_assembly_exception_count
            ),
            "newton": self.newton.to_dict(),
            "terminal_material_trial": self.terminal_material.to_dict(),
            "active": self._active,
        }

    def _read_clock(self) -> int:
        value = self.clock_ns()
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("clock_ns must return an integer nanosecond value")
        return value

    def _elapsed(self, started_ns: int) -> int:
        finished_ns = self._read_clock()
        if finished_ns < started_ns:
            raise ValueError("clock_ns must be monotonic")
        return finished_ns - started_ns

    def _begin_run(self) -> int:
        if self._active:
            raise ValueError("runtime recorder is already active")
        started_ns = self._read_clock()
        self._active = True
        self.run_count += 1
        return started_ns

    def _finish_run(self, started_ns: int, *, raised: bool) -> None:
        try:
            self.total_wall_ns += self._elapsed(started_ns)
            if raised:
                self.exception_run_count += 1
            else:
                self.completed_run_count += 1
        finally:
            self._active = False

    def _begin_terminal_trial_assembly(self) -> int:
        if not self._active:
            raise ValueError("runtime recorder has no active load-step solve")
        return self._read_clock()

    def _finish_terminal_trial_assembly(
        self,
        started_ns: int,
        *,
        raised: bool,
    ) -> None:
        self.terminal_trial_assembly_wall_ns += self._elapsed(started_ns)
        self.terminal_trial_assembly_call_count += 1
        if raised:
            self.terminal_trial_assembly_exception_count += 1


@dataclass(frozen=True)
class StatefulFiberFrame2DLoadStepAdapter:
    problem: StatefulFiberFrame2DProblem
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint
    target_load_factor: float
    initial_free_coordinates_override_m: tuple[float, ...] | None = None
    runtime_recorder: StatefulFiberFrame2DLoadStepRuntimeRecorder | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def case_id(self) -> str:
        return f"{self.problem.case_id}@load={self.target_load_factor:.12g}"

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        if self.initial_free_coordinates_override_m is not None:
            return np.asarray(
                self.initial_free_coordinates_override_m,
                dtype=np.float64,
            )
        scale = self.problem.physical_coordinate_scale
        global_displacements = np.asarray(
            self.accepted_checkpoint.global_displacements,
            dtype=np.float64,
        )
        generalized = global_displacements / scale
        return generalized[list(self.problem.free_global_dofs)].copy()

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.runtime_recorder is None:
            assembly = assemble_stateful_fiber_frame2d(
                self.problem,
                self.accepted_checkpoint,
                target_load_factor=self.target_load_factor,
                trial_free_coordinates_m=free_displacements_m,
            )
            return assembly.residual_kn, assembly.jacobian_kn_per_m

        started_ns = self.runtime_recorder.newton._begin_assemble()
        raised = False
        try:
            assembly = assemble_stateful_fiber_frame2d(
                self.problem,
                self.accepted_checkpoint,
                target_load_factor=self.target_load_factor,
                trial_free_coordinates_m=free_displacements_m,
                material_runtime=self.runtime_recorder.newton.material,
            )
        except BaseException:
            raised = True
            raise
        finally:
            self.runtime_recorder.newton._finish_assemble(
                started_ns,
                raised=raised,
            )
        return assembly.residual_kn, assembly.jacobian_kn_per_m


@dataclass(frozen=True)
class StatefulFiberFrame2DLoadStepResult:
    status: str
    committed: bool
    parent_checkpoint: StatefulFiberFrame2DCheckpoint
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint
    trial_solution: NewtonRaphsonVectorSolution
    trial_assembly: StatefulFiberFrame2DAssembly
    metrics: dict[str, Any]
    initial_free_coordinates_m: tuple[float, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "committed": self.committed,
            "parent_checkpoint": self.parent_checkpoint.to_dict(),
            "accepted_checkpoint": self.accepted_checkpoint.to_dict(),
            "trial_solution": {
                "status": self.trial_solution.status,
                "metrics": self.trial_solution.metrics,
                "convergence_history": self.trial_solution.convergence_history,
                "line_search_history": self.trial_solution.line_search_history,
                "unsupported_features": self.trial_solution.unsupported_features,
            },
            "trial_assembly": self.trial_assembly.to_dict(),
            "metrics": dict(self.metrics),
        }
        if self.initial_free_coordinates_m is not None:
            payload["initial_free_coordinates_m"] = list(
                self.initial_free_coordinates_m
            )
        return payload


def _assemble_terminal_trial(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    target_load_factor: float,
    free_coordinates_m: np.ndarray,
    *,
    runtime_recorder: StatefulFiberFrame2DLoadStepRuntimeRecorder | None,
) -> StatefulFiberFrame2DAssembly:
    if runtime_recorder is None:
        return assemble_stateful_fiber_frame2d(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free_coordinates_m,
        )
    started_ns = runtime_recorder._begin_terminal_trial_assembly()
    raised = False
    try:
        return assemble_stateful_fiber_frame2d(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free_coordinates_m,
            material_runtime=runtime_recorder.terminal_material,
        )
    except BaseException:
        raised = True
        raise
    finally:
        runtime_recorder._finish_terminal_trial_assembly(
            started_ns,
            raised=raised,
        )


def _solve_newton(
    adapter: StatefulFiberFrame2DLoadStepAdapter,
    config: NewtonRaphsonConfig,
    *,
    runtime_recorder: StatefulFiberFrame2DLoadStepRuntimeRecorder | None,
) -> NewtonRaphsonVectorSolution:
    if runtime_recorder is None:
        return newton_raphson_vector(adapter, config=config)

    started_ns = runtime_recorder.newton._begin_run()
    raised = False
    try:
        return newton_raphson_vector(
            adapter, config=config, increment_runtime=runtime_recorder.newton.increment
        )
    except BaseException:
        raised = True
        raise
    finally:
        runtime_recorder.newton._finish_run(started_ns, raised=raised)


def solve_stateful_fiber_frame2d_load_step(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    config: NewtonRaphsonConfig | None = None,
    initial_free_coordinates_m: Sequence[float] | np.ndarray | None = None,
    runtime_recorder: StatefulFiberFrame2DLoadStepRuntimeRecorder | None = None,
) -> StatefulFiberFrame2DLoadStepResult:
    """Solve one load target and atomically commit or exactly roll back.

    ``initial_free_coordinates_m`` is an optional Newton initial guess in the
    problem's generalized free coordinates.  It does not alter the accepted
    material state used to assemble trial responses.
    """

    if runtime_recorder is not None and not isinstance(
        runtime_recorder,
        StatefulFiberFrame2DLoadStepRuntimeRecorder,
    ):
        raise ValueError(
            "runtime_recorder must be a "
            "StatefulFiberFrame2DLoadStepRuntimeRecorder or None"
        )
    if runtime_recorder is None:
        return _solve_stateful_fiber_frame2d_load_step(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            config=config,
            initial_free_coordinates_m=initial_free_coordinates_m,
            runtime_recorder=None,
        )

    started_ns = runtime_recorder._begin_run()
    raised = False
    try:
        return _solve_stateful_fiber_frame2d_load_step(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            config=config,
            initial_free_coordinates_m=initial_free_coordinates_m,
            runtime_recorder=runtime_recorder,
        )
    except BaseException:
        raised = True
        raise
    finally:
        runtime_recorder._finish_run(started_ns, raised=raised)


def _solve_stateful_fiber_frame2d_load_step(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    config: NewtonRaphsonConfig | None,
    initial_free_coordinates_m: Sequence[float] | np.ndarray | None,
    runtime_recorder: StatefulFiberFrame2DLoadStepRuntimeRecorder | None,
) -> StatefulFiberFrame2DLoadStepResult:
    validate_stateful_fiber_frame2d_checkpoint(problem, accepted_checkpoint)
    parent_bytes = accepted_checkpoint.canonical_bytes()
    load_factor = _finite(target_load_factor, name="target_load_factor")
    initial_override: tuple[float, ...] | None = None
    if initial_free_coordinates_m is not None:
        initial_override = _normalize_initial_free_coordinates_m(
            problem,
            initial_free_coordinates_m,
        )
    adapter = StatefulFiberFrame2DLoadStepAdapter(
        problem=problem,
        accepted_checkpoint=accepted_checkpoint,
        target_load_factor=load_factor,
        initial_free_coordinates_override_m=initial_override,
        runtime_recorder=runtime_recorder,
    )
    solution = _solve_newton(
        adapter,
        config or NewtonRaphsonConfig(),
        runtime_recorder=runtime_recorder,
    )
    trial_assembly = _assemble_terminal_trial(
        problem,
        accepted_checkpoint,
        load_factor,
        solution.free_displacements_m,
        runtime_recorder=runtime_recorder,
    )
    no_solve_reaction_only = bool(
        solution.metrics.get("terminal_disposition")
        == NO_SOLVE_REACTION_ONLY_DISPOSITION
        and solution.metrics.get("solver_executed") is False
        and solution.metrics.get("active_equation_count") == 0
        and solution.metrics.get("assembly_contract_valid") is True
        and solution.metrics.get("convergence_claim") is False
    )
    iterative_solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and solution.metrics.get("residual_gate_passed") is True
        and solution.metrics.get("increment_gate_passed") is True
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
    )
    parent_binding = bool(
        trial_assembly.parent_checkpoint_hash == accepted_checkpoint.state_hash
        and all(
            row.response.parent_state_hash == parent.state_hash
            for row, parent in zip(
                trial_assembly.member_assemblies,
                accepted_checkpoint.element_states,
                strict=True,
            )
        )
    )
    parent_immutable = bool(
        accepted_checkpoint.canonical_bytes() == parent_bytes
        and accepted_checkpoint.compute_state_hash() == accepted_checkpoint.state_hash
    )
    solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and (no_solve_reaction_only or iterative_solver_contract)
        and parent_binding
        and parent_immutable
    )
    if solver_contract:
        next_checkpoint = StatefulFiberFrame2DCheckpoint(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            epoch=accepted_checkpoint.epoch + 1,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=load_factor,
            parent_state_hash=accepted_checkpoint.state_hash,
            global_displacements=tuple(
                float(value) for value in trial_assembly.global_displacements
            ),
            element_states=trial_assembly.trial_element_states,
        )
        validate_stateful_fiber_frame2d_checkpoint(problem, next_checkpoint)
        committed = True
        rollback_exact: bool | None = None
    else:
        next_checkpoint = accepted_checkpoint
        committed = False
        rollback_exact = bool(
            next_checkpoint is accepted_checkpoint
            and next_checkpoint.state_hash == accepted_checkpoint.state_hash
            and next_checkpoint.canonical_bytes() == parent_bytes
        )
    return StatefulFiberFrame2DLoadStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_checkpoint=accepted_checkpoint,
        accepted_checkpoint=next_checkpoint,
        trial_solution=solution,
        trial_assembly=trial_assembly,
        metrics={
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "target_load_factor": load_factor,
            "parent_checkpoint_hash": accepted_checkpoint.state_hash,
            "parent_epoch": accepted_checkpoint.epoch,
            "accepted_checkpoint_hash_after": next_checkpoint.state_hash,
            "accepted_epoch_after": next_checkpoint.epoch,
            "trial_parent_checkpoint_hash": trial_assembly.parent_checkpoint_hash,
            "section_and_element_parent_binding_passed": parent_binding,
            "parent_checkpoint_immutable": parent_immutable,
            "solver_contract_pass": solver_contract,
            "iterative_solver_contract_pass": iterative_solver_contract,
            "no_solve_contract_pass": no_solve_reaction_only,
            "terminal_disposition": solution.metrics.get(
                "terminal_disposition",
                SOLVE_FREE_EQUATIONS_DISPOSITION,
            ),
            "terminal_reason": solution.metrics.get("terminal_reason"),
            "residual_gate_passed": solution.metrics.get("residual_gate_passed"),
            "increment_gate_passed": solution.metrics.get("increment_gate_passed"),
            "regularization_used": bool(solution.metrics.get("regularization_used")),
            "fallback_used": bool(solution.metrics.get("fallback_used")),
            "committed": committed,
            "rollback_exact": rollback_exact,
            "yielded_member_count": sum(
                int(row.response.yielded_integration_point_count > 0)
                for row in trial_assembly.member_assemblies
            ),
            "damaged_member_count": sum(
                int(row.response.damaged_integration_point_count > 0)
                for row in trial_assembly.member_assemblies
            ),
        },
        initial_free_coordinates_m=initial_override,
    )


@dataclass(frozen=True)
class StatefulFiberFrame2DLoadPathResult:
    status: str
    initial_checkpoint: StatefulFiberFrame2DCheckpoint
    final_checkpoint: StatefulFiberFrame2DCheckpoint
    steps: tuple[StatefulFiberFrame2DLoadStepResult, ...] = field(default_factory=tuple)

    @property
    def contract_pass(self) -> bool:
        return bool(self.steps and all(step.committed for step in self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract_pass": self.contract_pass,
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
        }


def run_stateful_fiber_frame2d_load_path(
    problem: StatefulFiberFrame2DProblem,
    load_factors: Iterable[float],
    *,
    initial_checkpoint: StatefulFiberFrame2DCheckpoint | None = None,
    config: NewtonRaphsonConfig | None = None,
    initial_free_coordinates_by_step: (
        Iterable[Sequence[float] | np.ndarray | None] | None
    ) = None,
) -> StatefulFiberFrame2DLoadPathResult:
    factors = tuple(_finite(value, name="load_factor") for value in load_factors)
    if not factors:
        raise ValueError("load_factors must be non-empty")
    if initial_free_coordinates_by_step is None:
        initial_coordinates: tuple[tuple[float, ...] | None, ...] = (None,) * len(
            factors
        )
    else:
        try:
            provided_coordinates = tuple(initial_free_coordinates_by_step)
        except TypeError as exc:
            raise ValueError(
                "initial_free_coordinates_by_step must be an iterable"
            ) from exc
        if len(provided_coordinates) != len(factors):
            raise ValueError(
                "initial_free_coordinates_by_step must have exactly "
                f"{len(factors)} entries, got {len(provided_coordinates)}"
            )
        initial_coordinates = tuple(
            None
            if values is None
            else _normalize_initial_free_coordinates_m(
                problem,
                values,
                name=f"initial_free_coordinates_by_step[{index}]",
            )
            for index, values in enumerate(provided_coordinates)
        )
    first = initial_checkpoint or initial_stateful_fiber_frame2d_checkpoint(problem)
    validate_stateful_fiber_frame2d_checkpoint(problem, first)
    accepted = first
    rows: list[StatefulFiberFrame2DLoadStepResult] = []
    for factor, initial_coordinates_m in zip(
        factors,
        initial_coordinates,
        strict=True,
    ):
        step = solve_stateful_fiber_frame2d_load_step(
            problem,
            accepted,
            target_load_factor=factor,
            config=config,
            initial_free_coordinates_m=initial_coordinates_m,
        )
        rows.append(step)
        if not step.committed:
            return StatefulFiberFrame2DLoadPathResult(
                status="blocked",
                initial_checkpoint=first,
                final_checkpoint=accepted,
                steps=tuple(rows),
            )
        accepted = step.accepted_checkpoint
    return StatefulFiberFrame2DLoadPathResult(
        status="ready",
        initial_checkpoint=first,
        final_checkpoint=accepted,
        steps=tuple(rows),
    )


__all__ = [
    "StatefulFiberFrame2DLoadPathResult",
    "StatefulFiberFrame2DLoadStepAdapter",
    "StatefulFiberFrame2DLoadStepRuntimeRecorder",
    "StatefulFiberFrame2DLoadStepResult",
    "run_stateful_fiber_frame2d_load_path",
    "solve_stateful_fiber_frame2d_load_step",
]
