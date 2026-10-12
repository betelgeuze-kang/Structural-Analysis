"""Explicit source-ordinal schedule and independent dead-global load control.

The nested v1 checkpoint is a geometry/material projection. Only this profile's
mechanical wrapper binds its accepted independent load, full path and source.
Legacy frame/observation/public contracts are not reinterpreted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    StatefulCorotationalFiberFrame2DAssembly,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    LinearPhysicalDisplacementObservation,
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    _free_generalized_coordinates,
    _exact_float64_equal,
    _require_connected_member_graph,
    _solve_corotational_augmented_control,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

PROFILE = "source-ordinal-independent-dead-load-corotational-control.v1"
MAX_RECORDS = 65536
MAX_SOLVER_ATTEMPTS = 1000000
FORMULA = "R=R_base-S_f*P*b_axial;control=w*(c*u-g_target)"
LOAD_COLUMN = "dR/dlambda=base_assembled_dR/dlambda;dg/dlambda=c_p*ubar_p"
FORMULA_HASH = canonical_hash(
    {
        "profile": PROFILE,
        "formula": FORMULA,
        "lambda_column": LOAD_COLUMN,
        "accepted_state_equilibrium_scale": "max(base_reference_scale, norm_inf(S*P*b))",
    }
)
HASH_ZERO = "sha256:" + "0" * 64


def number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or (
        type(value) is int and abs(value) > 2**53 - 1
    ):
        raise ValueError(f"{name} must be a safe finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a safe finite number")
    return result


def integer(value: Any, name: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower},{upper}]")
    return value


def hash_field(value: Any, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(c not in "0123456789abcdef" for c in value[7:])
    ):
        raise ValueError(f"{name} must be a prefixed SHA-256")
    return value


def json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


@dataclass(frozen=True)
class HistoryRow:
    ordinal: int
    source_row: int
    source_row_sha256: str
    target_m: float
    axial_load_kn: float

    def __post_init__(self):
        integer(self.ordinal, "ordinal", 0, MAX_RECORDS - 1)
        integer(self.source_row, "source_row", 0, 2**53 - 1)
        hash_field(self.source_row_sha256, "source_row_sha256")
        object.__setattr__(self, "target_m", number(self.target_m, "target_m"))
        object.__setattr__(
            self, "axial_load_kn", number(self.axial_load_kn, "axial_load_kn")
        )

    def to_dict(self):
        return dict(
            ordinal=self.ordinal,
            source_row=self.source_row,
            source_row_sha256=self.source_row_sha256,
            target_m=self.target_m,
            axial_load_kn=self.axial_load_kn,
        )


@dataclass(frozen=True)
class OrdinalHistoryPlan:
    rows: tuple[HistoryRow, ...]
    source_id: str
    source_sha256: str
    mapping_hash: str
    hash: str = field(init=False)
    _hold_run_start: tuple[int, ...] = field(init=False, repr=False)
    _solve_prefix_count: tuple[int, ...] = field(init=False, repr=False)

    def __post_init__(self):
        if (
            type(self.rows) is not tuple
            or not 1 <= len(self.rows) <= MAX_RECORDS
            or any(type(r) is not HistoryRow for r in self.rows)
        ):
            raise ValueError("history requires 1 to 65536 exact HistoryRow records")
        if (
            type(self.source_id) is not str
            or not self.source_id
            or len(self.source_id) > 2048
        ):
            raise ValueError("source_id must be explicit and bounded")
        hash_field(self.source_sha256, "source_sha256")
        hash_field(self.mapping_hash, "mapping_hash")
        if tuple(r.ordinal for r in self.rows) != tuple(range(len(self.rows))):
            raise ValueError("history ordinals must be complete and ordered from zero")
        if any(a.source_row >= b.source_row for a, b in zip(self.rows, self.rows[1:])):
            raise ValueError("source rows must be strictly increasing")
        starts = []
        prefix = [0]
        for i, row in enumerate(self.rows):
            same = i > 0 and (row.target_m, row.axial_load_kn) == (
                self.rows[i - 1].target_m,
                self.rows[i - 1].axial_load_kn,
            )
            starts.append(starts[-1] if same else i)
            prefix.append(prefix[-1] + (not same))
        object.__setattr__(self, "_hold_run_start", tuple(starts))
        object.__setattr__(self, "_solve_prefix_count", tuple(prefix))
        object.__setattr__(self, "hash", canonical_hash(self.to_dict()))

    def to_dict(self):
        return {
            "schema": "source-ordinal-history-plan.v1",
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "mapping_hash": self.mapping_hash,
            "rows": [r.to_dict() for r in self.rows],
        }


@dataclass(frozen=True)
class ScheduledFrameProblem:
    frame_problem: StatefulCorotationalFiberFrame2DProblem
    observation: LinearPhysicalDisplacementObservation
    axial_load_pattern: tuple[tuple[int, float], ...]
    hash: str = field(init=False)
    _pattern: tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self):
        if (
            type(self.frame_problem) is not StatefulCorotationalFiberFrame2DProblem
            or type(self.observation) is not LinearPhysicalDisplacementObservation
        ):
            raise ValueError(
                "scheduled problem requires exact frame and observation types"
            )
        _require_connected_member_graph(self.frame_problem)
        self.observation.validate(self.frame_problem)
        if (
            type(self.axial_load_pattern) is not tuple
            or not 1 <= len(self.axial_load_pattern) <= 32
        ):
            raise ValueError("axial pattern requires 1 to 32 explicit terms")
        terms = []
        seen = set()
        vector = [0.0] * self.frame_problem.global_dof_count
        for row in self.axial_load_pattern:
            if type(row) is not tuple or len(row) != 2:
                raise ValueError(
                    "axial pattern term must be a (global_dof,coefficient) tuple"
                )
            dof, c = row
            integer(dof, "axial global_dof", 0, len(vector) - 1)
            if dof % 3 == 2 or dof in seen:
                raise ValueError(
                    "axial pattern requires distinct translational global DOFs"
                )
            c = number(c, "axial coefficient")
            if c == 0.0:
                raise ValueError("axial coefficients must be nonzero")
            seen.add(dof)
            terms.append((dof, c))
            vector[dof] = c
        object.__setattr__(self, "axial_load_pattern", tuple(sorted(terms)))
        object.__setattr__(self, "_pattern", tuple(vector))
        object.__setattr__(
            self,
            "hash",
            canonical_hash(
                {
                    "profile": PROFILE,
                    "base_problem": self.frame_problem.contract_hash,
                    "observation": self.observation.to_dict(),
                    "independent_dead_global_axial_pattern": self.axial_load_pattern,
                    "axial_unit": "kN",
                    "support_context": "legacy-proportional-lambda-only",
                }
            ),
        )

    def pattern(self):
        return np.asarray(self._pattern, dtype=np.float64)


def accepted_state_force_scale(problem, axial_load_kn):
    magnitude = abs(number(axial_load_kn, "accepted axial load"))
    with np.errstate(over="ignore", invalid="ignore"):
        value = float(
            np.linalg.norm(
                problem.frame_problem.physical_coordinate_scale
                * problem.pattern()
                * magnitude,
                ord=np.inf,
            )
        )
    if not math.isfinite(value):
        raise ValueError("independent force scale is not finite")
    return max(problem.frame_problem.reference_force_scale(), value)


@dataclass(frozen=True)
class ScheduledMechanicalCheckpoint:
    context_hash: str
    frame_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    axial_load_kn: float
    certified: bool
    last_mechanical_ordinal: int
    position_numerator: int
    position_depth: int
    prescribed_target_m: float
    parent_hash: str | None
    state_hash: str = field(init=False)

    def __post_init__(self):
        hash_field(self.context_hash, "context_hash")
        if (
            type(self.frame_checkpoint)
            is not StatefulCorotationalFiberFrame2DCheckpoint
        ):
            raise ValueError(
                "scheduled checkpoint needs an exact constitutive frame projection"
            )
        if type(self.certified) is not bool:
            raise ValueError("certified must be boolean")
        integer(
            self.last_mechanical_ordinal, "last_mechanical_ordinal", -1, MAX_RECORDS - 1
        )
        integer(self.position_depth, "position_depth", 0, 20)
        integer(
            self.position_numerator, "position_numerator", 0, 2**self.position_depth
        )
        object.__setattr__(
            self, "axial_load_kn", number(self.axial_load_kn, "accepted axial load")
        )
        object.__setattr__(
            self,
            "prescribed_target_m",
            number(self.prescribed_target_m, "accepted target"),
        )
        if self.parent_hash is not None:
            hash_field(self.parent_hash, "parent_hash")
        object.__setattr__(self, "state_hash", canonical_hash(self.semantic_dict()))

    def semantic_dict(self):
        return {
            "schema": "scheduled-corotational-mechanical-checkpoint.v1",
            "context_hash": self.context_hash,
            "constitutive_frame_state_hash": self.frame_checkpoint.state_hash,
            "load_context": {
                "axial_load_kn": self.axial_load_kn,
                "lambda": self.frame_checkpoint.load_factor,
            },
            "certified": self.certified,
            "last_mechanical_ordinal": self.last_mechanical_ordinal,
            "position_numerator": self.position_numerator,
            "position_depth": self.position_depth,
            "prescribed_target_m": self.prescribed_target_m,
            "parent_hash": self.parent_hash,
        }

    def canonical_bytes(self):
        return (
            json_bytes(self.semantic_dict())
            + b"\0"
            + self.frame_checkpoint.canonical_bytes()
        )


def validate_mechanical_checkpoint(problem, context_hash, state):
    if (
        type(state) is not ScheduledMechanicalCheckpoint
        or state.context_hash != context_hash
    ):
        raise ValueError("scheduled checkpoint context/type mismatch")
    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem.frame_problem, state.frame_checkpoint
    )
    if state.state_hash != canonical_hash(state.semantic_dict()):
        raise ValueError("scheduled checkpoint state hash mismatch")
    if state.certified:
        if (
            state.frame_checkpoint.epoch < 1
            or state.last_mechanical_ordinal < 0
            or state.position_numerator == 0
            or state.parent_hash is None
        ):
            raise ValueError("certified scheduled state has invalid ancestry/position")
    elif (
        state.canonical_bytes()
        != initial_mechanical_checkpoint(problem, context_hash).canonical_bytes()
    ):
        raise ValueError("uncertified scheduled state must be exact genesis")


def initial_mechanical_checkpoint(problem, context_hash):
    frame = initial_stateful_corotational_fiber_frame2d_checkpoint(
        problem.frame_problem
    )
    return ScheduledMechanicalCheckpoint(
        context_hash,
        frame,
        0.0,
        False,
        -1,
        0,
        0,
        problem.observation.evaluate(frame.global_displacements),
        None,
    )


@dataclass(frozen=True)
class ScheduledFrameAssembly:
    constitutive_trial: StatefulCorotationalFiberFrame2DAssembly
    axial_load_kn: float
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    residual_kn: np.ndarray

    def __post_init__(self):
        number(self.axial_load_kn, "assembled axial load")
        for name in ("external_loads_global", "reactions_global", "residual_kn"):
            value = np.ascontiguousarray(getattr(self, name), dtype=np.float64).copy()
            if not np.all(np.isfinite(value)):
                raise ValueError("nonfinite scheduled assembly")
            value.setflags(write=False)
            object.__setattr__(self, name, value)

    @property
    def global_displacements(self):
        return self.constitutive_trial.global_displacements

    @property
    def generalized_coordinates_m(self):
        return self.constitutive_trial.generalized_coordinates_m

    @property
    def jacobian_kn_per_m(self):
        return self.constitutive_trial.jacobian_kn_per_m

    @property
    def residual_load_factor_derivative_kn(self):
        return self.constitutive_trial.residual_load_factor_derivative_kn


def assemble_scheduled_frame(
    problem,
    parent,
    context_hash,
    *,
    target_axial_load_kn,
    target_load_factor,
    trial_free_coordinates_m,
):
    validate_mechanical_checkpoint(problem, context_hash, parent)
    p = number(target_axial_load_kn, "target axial load")
    frame = assemble_stateful_corotational_fiber_frame2d(
        problem.frame_problem,
        parent.frame_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=trial_free_coordinates_m,
    )
    with np.errstate(over="ignore", invalid="ignore"):
        independent = p * problem.pattern()
        external = frame.external_loads_global + independent
    if not np.all(np.isfinite(external)):
        raise ValueError("scheduled external load is not finite")
    physical = frame.internal_loads_global - external
    dofs = list(problem.frame_problem.free_global_dofs)
    scale = problem.frame_problem.physical_coordinate_scale
    residual = scale[dofs] * physical[dofs]
    reactions = np.zeros(problem.frame_problem.global_dof_count)
    fixed = list(problem.frame_problem.fixed_global_dofs)
    reactions[fixed] = physical[fixed]
    return ScheduledFrameAssembly(frame, p, external, reactions, residual)


@dataclass(frozen=True)
class ScheduledAugmentedAssembly:
    frame_assembly: ScheduledFrameAssembly
    augmented_coordinates_m: np.ndarray
    augmented_residual_kn: np.ndarray
    augmented_jacobian_kn_per_m: np.ndarray
    load_factor_residual_derivative_kn: np.ndarray
    control_error_m: float
    control_reference_m: float
    control_equation_scale_kn_per_m: float


@dataclass(frozen=True)
class ScheduledControlStepProblem:
    scheduled: ScheduledFrameProblem
    parent: ScheduledMechanicalCheckpoint
    context_hash: str
    target_control_displacement_m: float
    target_axial_load_kn: float
    config: StatefulCorotationalFiberFrame2DDisplacementControlConfig
    assembly_count: list[int] = field(
        default_factory=lambda: [0], compare=False, repr=False
    )

    def __post_init__(self):
        validate_mechanical_checkpoint(self.scheduled, self.context_hash, self.parent)
        object.__setattr__(
            self,
            "target_control_displacement_m",
            number(self.target_control_displacement_m, "target control"),
        )
        object.__setattr__(
            self,
            "target_axial_load_kn",
            number(self.target_axial_load_kn, "target axial"),
        )
        if (
            type(self.config)
            is not StatefulCorotationalFiberFrame2DDisplacementControlConfig
        ):
            raise ValueError("invalid solver config")

    @property
    def problem(self):
        return self

    @property
    def node_coordinates_m(self):
        return self.scheduled.frame_problem.node_coordinates_m

    @property
    def members(self):
        return self.scheduled.frame_problem.members

    @property
    def free_global_dofs(self):
        return self.scheduled.frame_problem.free_global_dofs

    @property
    def control_global_dof(self):
        return None

    @property
    def control_free_index(self):
        return None

    @property
    def control_observation(self):
        return self.scheduled.observation

    @property
    def profile(self):
        return PROFILE

    @property
    def formula_hash(self):
        return FORMULA_HASH

    @property
    def case_id(self):
        return (
            self.scheduled.frame_problem.case_id
            + "@ordinal-context="
            + self.context_hash
        )

    def reference_force_scale(self):
        return max(
            accepted_state_force_scale(self.scheduled, self.target_axial_load_kn),
            accepted_state_force_scale(self.scheduled, self.parent.axial_load_kn),
        )

    def initial_augmented_coordinates_m(self):
        return np.concatenate(
            (
                _free_generalized_coordinates(
                    self.scheduled.frame_problem, self.parent.frame_checkpoint
                ),
                [
                    self.parent.frame_checkpoint.load_factor
                    * self.config.load_factor_coordinate_scale_m
                ],
            )
        )

    def control_value(self, frame):
        return self.scheduled.observation.evaluate(frame.global_displacements)

    def assemble(self, coordinates):
        self.assembly_count[0] += 1
        x = np.asarray(coordinates, dtype=np.float64)
        if x.shape != (len(self.free_global_dofs) + 1,) or not np.all(np.isfinite(x)):
            raise ValueError("invalid scheduled augmented coordinates")
        lam = float(x[-1]) / self.config.load_factor_coordinate_scale_m
        frame = assemble_scheduled_frame(
            self.scheduled,
            self.parent,
            self.context_hash,
            target_axial_load_kn=self.target_axial_load_kn,
            target_load_factor=lam,
            trial_free_coordinates_m=x[:-1],
        )
        parent_g = self.scheduled.observation.evaluate(
            self.parent.frame_checkpoint.global_displacements
        )
        reference = max(
            abs(self.target_control_displacement_m),
            abs(self.target_control_displacement_m - parent_g),
            1e-6,
        )
        w = self.reference_force_scale() / reference
        error = self.control_value(frame) - self.target_control_displacement_m
        jac = np.zeros((len(x), len(x)))
        jac[:-1, :-1] = frame.jacobian_kn_per_m
        jac[:-1, -1] = (
            frame.residual_load_factor_derivative_kn
            / self.config.load_factor_coordinate_scale_m
        )
        jac[-1, :-1] = w * self.scheduled.observation.free_gradient(
            self.scheduled.frame_problem
        )
        jac[-1, -1] = (
            w
            * self.scheduled.observation.prescribed_load_derivative(
                self.scheduled.frame_problem
            )
            / self.config.load_factor_coordinate_scale_m
        )
        residual = np.concatenate((frame.residual_kn, [w * error]))
        return ScheduledAugmentedAssembly(
            frame,
            x.copy(),
            residual,
            jac,
            frame.residual_load_factor_derivative_kn,
            error,
            reference,
            w,
        )


@dataclass(frozen=True)
class ScheduledStepResult:
    committed: bool
    parent: ScheduledMechanicalCheckpoint
    accepted: ScheduledMechanicalCheckpoint
    solution: Any
    assembly: ScheduledFrameAssembly
    rollback_exact: bool | None
    assembly_count: int
    linear_solve_attempts: int


def solve_scheduled_control_step(
    problem,
    parent,
    context_hash,
    *,
    target_m,
    axial_load_kn,
    ordinal,
    position_numerator,
    position_depth,
    config,
    cost_counter=None,
    linear_counter=None,
):
    before = parent.canonical_bytes()
    step = ScheduledControlStepProblem(
        problem,
        parent,
        context_hash,
        target_m,
        axial_load_kn,
        config,
        [0] if cost_counter is None else cost_counter,
    )
    if linear_counter is None:
        linear_counter = {"linear_solve_attempts": 0}
    solution = _solve_corotational_augmented_control(
        step,
        augmented_formula=FORMULA,
        load_column_formula=LOAD_COLUMN,
        work_counters=linear_counter,
        terminal_equilibrium_scale_kn=accepted_state_force_scale(
            problem, step.target_axial_load_kn
        ),
    )
    # Reassemble the COMPLETE scheduled response, never the old base-only commit.
    step.assembly_count[0] += 1
    trial = assemble_scheduled_frame(
        problem,
        parent,
        context_hash,
        target_axial_load_kn=axial_load_kn,
        target_load_factor=solution.load_factor,
        trial_free_coordinates_m=solution.free_displacements_m,
    )
    frame = trial.constitutive_trial
    immutable = parent.canonical_bytes() == before
    binding = (
        frame.parent_checkpoint_hash == parent.frame_checkpoint.state_hash
        and all(
            m.response.parent_state_hash == s.state_hash
            for m, s in zip(
                frame.member_assemblies,
                parent.frame_checkpoint.element_states,
                strict=True,
            )
        )
    )
    coordinates = _exact_float64_equal(
        solution.free_displacements_m,
        frame.generalized_coordinates_m[list(problem.frame_problem.free_global_dofs)],
    )
    residual_binding = _exact_float64_equal(
        solution.metrics.get("residual_kn", ()), trial.residual_kn
    )
    actual_gate = (
        abs(
            problem.observation.evaluate(frame.global_displacements)
            - step.target_control_displacement_m
        )
        <= config.control_tolerance_m
    )
    eq = (
        float(np.linalg.norm(trial.residual_kn, ord=np.inf))
        / accepted_state_force_scale(problem, step.target_axial_load_kn)
        <= config.residual_tolerance
    )
    commit = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and solution.metrics.get("increment_gate_passed") is True
        and solution.metrics.get("residual_gate_passed") is True
        and solution.metrics.get("accepted_state_residual_gate_passed") is True
        and solution.metrics.get("control_gate_passed") is True
        and solution.metrics.get("fallback_used") is False
        and solution.metrics.get("regularization_used") is False
        and immutable
        and binding
        and coordinates
        and residual_binding
        and eq
        and actual_gate
        and trial.axial_load_kn == step.target_axial_load_kn
        and frame.target_load_factor == solution.load_factor
    )
    if commit:
        fc = StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=problem.frame_problem.case_id,
            problem_contract_hash=problem.frame_problem.contract_hash,
            epoch=parent.frame_checkpoint.epoch + 1,
            step_index=parent.frame_checkpoint.step_index + 1,
            load_factor=solution.load_factor,
            parent_state_hash=parent.frame_checkpoint.state_hash,
            global_displacements=tuple(float(v) for v in frame.global_displacements),
            element_states=frame.trial_element_states,
        )
        accepted = ScheduledMechanicalCheckpoint(
            context_hash,
            fc,
            step.target_axial_load_kn,
            True,
            ordinal,
            position_numerator,
            position_depth,
            step.target_control_displacement_m,
            parent.state_hash,
        )
        validate_mechanical_checkpoint(problem, context_hash, accepted)
    else:
        accepted = parent
    return ScheduledStepResult(
        commit,
        parent,
        accepted,
        solution,
        trial,
        None if commit else accepted is parent and accepted.canonical_bytes() == before,
        step.assembly_count[0],
        linear_counter["linear_solve_attempts"],
    )
