"""Stateful arc-length path for the bounded material-geometric two-bar truss.

Each physical arc-length attempt is evaluated from one immutable accepted
material parent.  A converged equilibrium and spherical-constraint pair
commits apex displacement, load factor, and both material states atomically;
a rejected attempt retains the exact accepted bytes before reducing the arc.

The default tangent solve intentionally materializes a dense 2x2 matrix.  A
bound external state-tangent solver may be supplied for integration evidence;
its profile and contract hash become part of the path/checkpoint identity.  The
physical loop remains a Level-1 verification bridge, not a general
truss/frame/shell formulation, production sparse solver, or ROCm/HIP backend.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import math
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar

from structural_analysis.benchmark.material_geometric_truss import (
    MATERIAL_GEOMETRIC_TRUSS_FORMULATION,
    StatefulTwoBarTrussAcceptedState,
    StatefulTwoBarTrussAssembly,
    StatefulTwoBarTrussProblem,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE,
    VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
    VectorArcLengthConfig,
    VectorArcLengthResult,
    VectorArcLengthStateTangentSolver,
    VectorArcLengthTangentSolve,
    build_vector_arc_length_path_contract_hash,
    create_vector_arc_length_checkpoint,
    vector_arc_length_continuation,
)


MATERIAL_GEOMETRIC_ARC_LENGTH_SCHEMA_VERSION = (
    "phase2-stateful-material-geometric-truss-arc-length.v1"
)
MATERIAL_GEOMETRIC_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION = (
    "phase2-stateful-material-geometric-truss-arc-length-checkpoint.v1"
)
MATERIAL_GEOMETRIC_ARC_LENGTH_PROFILE = (
    "accepted-material-geometric-parent-vector-arc-length-dense-2x2.v1"
)
MATERIAL_GEOMETRIC_ARC_LENGTH_EXTERNAL_SOLVER_PROFILE = (
    "accepted-material-geometric-parent-vector-arc-length-external-state-tangent.v1"
)
MATERIAL_GEOMETRIC_ARC_LENGTH_DENSE_SOLVER_PROFILE = (
    "material-geometric-truss-dense-state-tangent-solve.v1"
)
MATERIAL_GEOMETRIC_ARC_LENGTH_TANGENT_ACTION = (
    "assemble_two_bar_truss(accepted_material_parent,"
    "u_accepted+delta_u,lambda_accepted+delta_lambda)."
    "consistent_tangent_kn_per_m*direction_m"
)
MATERIAL_GEOMETRIC_ARC_LENGTH_CLAIM_BOUNDARY = (
    "This receipt verifies one symmetric planar two-bar truss whose exact "
    "current-chord geometry, combined-hardening steel states, material and "
    "initial-stress tangent terms, vector arc-length equilibrium, adaptive "
    "rollback, deterministic replay, and in-memory checkpoint restart are "
    "coupled at every accepted physical step. It does not validate a general "
    "2D/3D truss, frame or shell, finite-strain constitutive behavior, a "
    "durable checkpoint artifact, external code-to-code or experimental "
    "evidence, production sparse or ROCm/HIP execution, full-building "
    "equilibrium, or G1 closure."
)

MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG = VectorArcLengthConfig(
    target_monitor_dof_index=1,
    target_monitor_displacement_m=-0.05,
    target_direction=-1,
    initial_arc_length_m=0.008,
    minimum_arc_length_m=0.000125,
    maximum_arc_length_m=0.008,
    failed_step_reduction=0.5,
    load_factor_metric_scale_m=0.005,
    displacement_metric_weights=(1.0, 1.0),
    residual_tolerance_kn=1.0e-8,
    tangent_solve_residual_tolerance_kn=1.0e-8,
    constraint_tolerance_m2=1.0e-12,
    maximum_corrector_iterations=5,
    maximum_attempt_count=40,
)


class MaterialGeometricArcLengthError(ValueError):
    """Fail-closed bounded path or checkpoint error."""


def _finite_scalar(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise MaterialGeometricArcLengthError(f"{name} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MaterialGeometricArcLengthError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise MaterialGeometricArcLengthError(f"{name} must be finite")
    return result


def _vector2(values: Any, *, name: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise MaterialGeometricArcLengthError(
            f"{name} must be a finite two-vector"
        ) from exc
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise MaterialGeometricArcLengthError(f"{name} must be a finite two-vector")
    return np.ascontiguousarray(result, dtype=np.float64)


def _require_hash(value: Any, *, name: str) -> str:
    normalized = str(value)
    if (
        len(normalized) != 71
        or not normalized.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in normalized[7:])
    ):
        raise MaterialGeometricArcLengthError(
            f"{name} must be a canonical sha256 digest"
        )
    return normalized


def _json_safe(value: Any) -> Any:
    """Replace kernel sentinel infinities with explicit JSON null values."""

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _material_bytes(
    state: StatefulTwoBarTrussAcceptedState,
) -> tuple[bytes, bytes]:
    return tuple(item.canonical_bytes() for item in state.material_states)


def _source_problem_contract_hash(problem: StatefulTwoBarTrussProblem) -> str:
    material = problem.material
    return canonical_hash(
        {
            "case_id": problem.case_id,
            "formulation": MATERIAL_GEOMETRIC_TRUSS_FORMULATION,
            "half_span_m": problem.half_span_m,
            "rise_m": problem.rise_m,
            "area_m2": problem.area_m2,
            "reference_vertical_load_kn": problem.reference_vertical_load_kn,
            "material": {
                "material_id": material.material_id,
                "elastic_modulus_mpa": material.elastic_modulus_mpa,
                "yield_stress_mpa": material.yield_stress_mpa,
                "isotropic_hardening_modulus_mpa": (
                    material.isotropic_hardening_modulus_mpa
                ),
                "kinematic_hardening_modulus_mpa": (
                    material.kinematic_hardening_modulus_mpa
                ),
                "yield_tolerance_mpa": material.yield_tolerance_mpa,
            },
        }
    )


def build_material_geometric_source_problem_contract_hash(
    problem: StatefulTwoBarTrussProblem,
) -> str:
    """Return the canonical source identity shared by bounded solver adapters."""

    return _source_problem_contract_hash(problem)


def _metric_weights(config: VectorArcLengthConfig) -> np.ndarray:
    values = (
        np.ones(2, dtype=np.float64)
        if config.displacement_metric_weights is None
        else _vector2(
            config.displacement_metric_weights,
            name="displacement_metric_weights",
        )
    )
    if np.any(values <= 0.0):
        raise MaterialGeometricArcLengthError(
            "displacement_metric_weights must be positive"
        )
    return values


def _validate_config(config: VectorArcLengthConfig) -> np.ndarray:
    if config.target_monitor_dof_index != 1:
        raise MaterialGeometricArcLengthError(
            "the bounded path must monitor apex vertical displacement"
        )
    if config.target_direction != -1:
        raise MaterialGeometricArcLengthError(
            "the bounded path target_direction must be -1"
        )
    if (
        _finite_scalar(
            config.target_monitor_displacement_m,
            name="target_monitor_displacement_m",
        )
        >= 0.0
    ):
        raise MaterialGeometricArcLengthError(
            "target_monitor_displacement_m must be negative"
        )
    positive = {
        "initial_arc_length_m": config.initial_arc_length_m,
        "minimum_arc_length_m": config.minimum_arc_length_m,
        "maximum_arc_length_m": config.maximum_arc_length_m,
        "failed_step_reduction": config.failed_step_reduction,
        "load_factor_metric_scale_m": config.load_factor_metric_scale_m,
        "residual_tolerance_kn": config.residual_tolerance_kn,
        "tangent_solve_residual_tolerance_kn": (
            config.tangent_solve_residual_tolerance_kn
        ),
        "constraint_tolerance_m2": config.constraint_tolerance_m2,
    }
    for name, value in positive.items():
        if _finite_scalar(value, name=name) <= 0.0:
            raise MaterialGeometricArcLengthError(f"{name} must be positive")
    if not 0.0 < config.failed_step_reduction < 1.0:
        raise MaterialGeometricArcLengthError(
            "failed_step_reduction must lie between zero and one"
        )
    if not (
        config.minimum_arc_length_m
        <= config.initial_arc_length_m
        <= config.maximum_arc_length_m
    ):
        raise MaterialGeometricArcLengthError(
            "arc-length bounds must contain the initial arc length"
        )
    if (
        type(config.maximum_corrector_iterations) is not int
        or config.maximum_corrector_iterations < 1
        or type(config.maximum_attempt_count) is not int
        or config.maximum_attempt_count < 1
    ):
        raise MaterialGeometricArcLengthError(
            "iteration and attempt limits must be positive integers"
        )
    return _metric_weights(config)


def _dense_solver_contract_hash(problem: StatefulTwoBarTrussProblem) -> str:
    return canonical_hash(
        {
            "profile": MATERIAL_GEOMETRIC_ARC_LENGTH_DENSE_SOLVER_PROFILE,
            "source_problem_contract_hash": _source_problem_contract_hash(problem),
            "equation_count": 2,
            "matrix_storage": "numpy_dense_2x2",
            "linear_residual_tolerance_kn": 1.0e-10,
        }
    )


def build_material_geometric_arc_length_path_contract_hash(
    problem: StatefulTwoBarTrussProblem,
    config: VectorArcLengthConfig,
    *,
    state_tangent_solver: VectorArcLengthStateTangentSolver | None = None,
) -> str:
    """Bind source, controls, tangent action, and the selected state solver."""

    _validate_config(config)
    solver = (
        state_tangent_solver
        or create_dense_material_geometric_state_tangent_solver(problem)
    )
    solver_profile = str(solver.profile).strip()
    if not solver_profile:
        raise MaterialGeometricArcLengthError(
            "state tangent solver profile must be non-empty"
        )
    solver_contract_hash = _require_hash(
        solver.contract_hash,
        name="state_tangent_solver.contract_hash",
    )
    default_dense_solver = bool(
        solver_profile == MATERIAL_GEOMETRIC_ARC_LENGTH_DENSE_SOLVER_PROFILE
        and solver_contract_hash == _dense_solver_contract_hash(problem)
    )
    path_profile = (
        MATERIAL_GEOMETRIC_ARC_LENGTH_PROFILE
        if default_dense_solver
        else MATERIAL_GEOMETRIC_ARC_LENGTH_EXTERNAL_SOLVER_PROFILE
    )
    payload = {
        "schema_version": MATERIAL_GEOMETRIC_ARC_LENGTH_SCHEMA_VERSION,
        "profile": path_profile,
        "source_problem_contract_hash": _source_problem_contract_hash(problem),
        "config": asdict(config),
        "equilibrium_linearization_mode": (
            VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        ),
        "tangent_solver_mode": VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
        "tangent_solver_contract_hash": solver_contract_hash,
        "tangent_action": MATERIAL_GEOMETRIC_ARC_LENGTH_TANGENT_ACTION,
    }
    if not default_dense_solver:
        payload["tangent_solver_profile"] = solver_profile
    return canonical_hash(payload)


@dataclass(frozen=True)
class MaterialGeometricArcLengthStepProblem:
    """One local arc attempt bound to one accepted material parent."""

    problem: StatefulTwoBarTrussProblem
    accepted_state: StatefulTwoBarTrussAcceptedState
    attempt_arc_length_m: float

    def __post_init__(self) -> None:
        self.problem.validate_state(self.accepted_state)
        arc = _finite_scalar(
            self.attempt_arc_length_m,
            name="attempt_arc_length_m",
        )
        if arc <= 0.0:
            raise MaterialGeometricArcLengthError(
                "attempt_arc_length_m must be positive"
            )
        object.__setattr__(self, "attempt_arc_length_m", arc)

    @property
    def case_id(self) -> str:
        attempt_hash = canonical_hash(
            {
                "profile": MATERIAL_GEOMETRIC_ARC_LENGTH_PROFILE,
                "source_problem_contract_hash": _source_problem_contract_hash(
                    self.problem
                ),
                "accepted_state_hash": self.accepted_state.state_hash,
                "attempt_arc_length_m": self.attempt_arc_length_m,
            }
        )
        return f"{self.problem.case_id}@material-geometric-arc={attempt_hash}"

    @property
    def equation_count(self) -> int:
        return 2

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(2, dtype=np.float64)

    def initial_load_factor(self) -> float:
        return 0.0

    def actual_displacements_m(self, displacement_increments_m: Any) -> np.ndarray:
        increments = _vector2(
            displacement_increments_m,
            name="displacement_increments_m",
        )
        return np.ascontiguousarray(
            np.asarray(
                self.accepted_state.apex_displacements_m,
                dtype=np.float64,
            )
            + increments,
            dtype=np.float64,
        )

    def actual_load_factor(self, increment_load_factor: Any) -> float:
        return float(
            self.accepted_state.load_factor
            + _finite_scalar(
                increment_load_factor,
                name="increment_load_factor",
            )
        )

    def assemble(
        self,
        displacement_increments_m: Any,
        increment_load_factor: Any,
    ) -> StatefulTwoBarTrussAssembly:
        return self.problem.assemble(
            self.accepted_state,
            target_load_factor=self.actual_load_factor(increment_load_factor),
            trial_apex_displacements_m=self.actual_displacements_m(
                displacement_increments_m
            ),
        )

    def residual_kn(
        self,
        displacement_increments_m: np.ndarray,
        increment_load_factor: float,
    ) -> np.ndarray:
        return np.ascontiguousarray(
            self.assemble(
                displacement_increments_m,
                increment_load_factor,
            ).residual_kn,
            dtype=np.float64,
        )

    def negative_load_derivative_kn(
        self,
        displacement_increments_m: np.ndarray,
        increment_load_factor: float,
    ) -> np.ndarray:
        del displacement_increments_m, increment_load_factor
        return np.ascontiguousarray(
            self.problem.reference_load_kn(),
            dtype=np.float64,
        )

    def reference_load_kn(self) -> np.ndarray:
        return self.negative_load_derivative_kn(np.zeros(2), 0.0)

    def consistent_state_tangent_action_kn_per_m(
        self,
        displacement_increments_m: np.ndarray,
        increment_load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        direction = _vector2(direction_m, name="direction_m")
        return np.ascontiguousarray(
            self.assemble(
                displacement_increments_m,
                increment_load_factor,
            ).consistent_tangent_kn_per_m
            @ direction,
            dtype=np.float64,
        )


@dataclass(frozen=True)
class DenseMaterialGeometricStateTangentSolver:
    """Verification-only dense solve for the two-equation state operator."""

    profile: str
    contract_hash: str

    def solve_at_state(
        self,
        problem: MaterialGeometricArcLengthStepProblem,
        free_displacements_m: np.ndarray,
        right_hand_side_kn: np.ndarray,
        *,
        load_factor: float,
        solve_id: str,
    ) -> VectorArcLengthTangentSolve:
        if not isinstance(problem, MaterialGeometricArcLengthStepProblem):
            raise TypeError("dense solver received an incompatible problem")
        state = _vector2(free_displacements_m, name="free_displacements_m")
        right_hand_side = _vector2(
            right_hand_side_kn,
            name="right_hand_side_kn",
        )
        identity = np.eye(2, dtype=np.float64)
        tangent = np.column_stack(
            [
                problem.consistent_state_tangent_action_kn_per_m(
                    state,
                    load_factor,
                    identity[:, column],
                )
                for column in range(2)
            ]
        )
        try:
            solution = np.linalg.solve(tangent, right_hand_side)
        except np.linalg.LinAlgError:
            solution = np.zeros(2, dtype=np.float64)
            residual_inf = math.inf
            contract_pass = False
            terminal_reason = "dense_tangent_singular"
        else:
            residual_inf = float(
                np.linalg.norm(
                    tangent @ solution - right_hand_side,
                    ord=np.inf,
                )
            )
            contract_pass = bool(
                np.all(np.isfinite(solution)) and residual_inf <= 1.0e-10
            )
            terminal_reason = (
                "converged"
                if contract_pass
                else "dense_tangent_explicit_residual_failed"
            )
        operator_hash = canonical_hash(
            {
                "accepted_state_hash": problem.accepted_state.state_hash,
                "local_displacements_m": state.tolist(),
                "local_load_factor": float(load_factor),
                "tangent_kn_per_m": tangent.tolist(),
            }
        )
        return VectorArcLengthTangentSolve(
            profile=self.profile,
            contract_hash=self.contract_hash,
            contract_pass=contract_pass,
            terminal_reason=terminal_reason,
            solution_free=tuple(float(value) for value in solution),
            receipt={
                "schema_version": "dense-material-geometric-state-solve.v1",
                "contract_pass": contract_pass,
                "solve_id": solve_id,
                "operator_numeric_values_hash": operator_hash,
                "explicit_residual_inf_norm_kn": (
                    residual_inf if math.isfinite(residual_inf) else None
                ),
                "matrix_storage": "numpy_dense_2x2",
            },
        )


def create_dense_material_geometric_state_tangent_solver(
    problem: StatefulTwoBarTrussProblem,
) -> DenseMaterialGeometricStateTangentSolver:
    return DenseMaterialGeometricStateTangentSolver(
        profile=MATERIAL_GEOMETRIC_ARC_LENGTH_DENSE_SOLVER_PROFILE,
        contract_hash=_dense_solver_contract_hash(problem),
    )


def _checkpoint_payload(
    *,
    source_problem_contract_hash: str,
    path_contract_hash: str,
    accepted_state: StatefulTwoBarTrussAcceptedState,
    current_arc_length_m: float,
    previous_tangent_displacements: tuple[float, float] | None,
    previous_tangent_load_factor: float | None,
    attempt_count: int,
    last_attempt_outcome: str,
    last_attempt_stop_reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": (MATERIAL_GEOMETRIC_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION),
        "source_problem_contract_hash": source_problem_contract_hash,
        "path_contract_hash": path_contract_hash,
        "accepted_state_hash": accepted_state.state_hash,
        "current_arc_length_m": current_arc_length_m,
        "previous_tangent_displacements": (
            None
            if previous_tangent_displacements is None
            else list(previous_tangent_displacements)
        ),
        "previous_tangent_load_factor": previous_tangent_load_factor,
        "attempt_count": attempt_count,
        "last_attempt_outcome": last_attempt_outcome,
        "last_attempt_stop_reason": last_attempt_stop_reason,
    }


@dataclass(frozen=True)
class MaterialGeometricArcLengthCheckpoint:
    source_problem_contract_hash: str
    path_contract_hash: str
    accepted_state: StatefulTwoBarTrussAcceptedState
    current_arc_length_m: float
    previous_tangent_displacements: tuple[float, float] | None
    previous_tangent_load_factor: float | None
    attempt_count: int
    last_attempt_outcome: str
    last_attempt_stop_reason: str
    checkpoint_hash: str = ""

    def __post_init__(self) -> None:
        _require_hash(
            self.source_problem_contract_hash,
            name="source_problem_contract_hash",
        )
        _require_hash(self.path_contract_hash, name="path_contract_hash")
        if self.accepted_state.compute_state_hash() != self.accepted_state.state_hash:
            raise MaterialGeometricArcLengthError(
                "checkpoint accepted state hash is invalid"
            )
        arc = _finite_scalar(
            self.current_arc_length_m,
            name="current_arc_length_m",
        )
        if arc <= 0.0:
            raise MaterialGeometricArcLengthError(
                "current_arc_length_m must be positive"
            )
        if type(self.attempt_count) is not int or self.attempt_count < 0:
            raise MaterialGeometricArcLengthError(
                "attempt_count must be a non-negative integer"
            )
        if not str(self.last_attempt_outcome).strip():
            raise MaterialGeometricArcLengthError(
                "last_attempt_outcome must be non-empty"
            )
        if not str(self.last_attempt_stop_reason).strip():
            raise MaterialGeometricArcLengthError(
                "last_attempt_stop_reason must be non-empty"
            )
        previous_displacements = self.previous_tangent_displacements
        previous_load = self.previous_tangent_load_factor
        if (previous_displacements is None) != (previous_load is None):
            raise MaterialGeometricArcLengthError(
                "previous tangent fields must both be present or absent"
            )
        if previous_displacements is not None:
            normalized = tuple(
                float(value)
                for value in _vector2(
                    previous_displacements,
                    name="previous_tangent_displacements",
                )
            )
            object.__setattr__(self, "previous_tangent_displacements", normalized)
            normalized_load = _finite_scalar(
                previous_load,
                name="previous_tangent_load_factor",
            )
            object.__setattr__(
                self,
                "previous_tangent_load_factor",
                normalized_load,
            )
        object.__setattr__(self, "current_arc_length_m", arc)
        expected = canonical_hash(
            _checkpoint_payload(
                source_problem_contract_hash=self.source_problem_contract_hash,
                path_contract_hash=self.path_contract_hash,
                accepted_state=self.accepted_state,
                current_arc_length_m=arc,
                previous_tangent_displacements=(self.previous_tangent_displacements),
                previous_tangent_load_factor=self.previous_tangent_load_factor,
                attempt_count=self.attempt_count,
                last_attempt_outcome=self.last_attempt_outcome,
                last_attempt_stop_reason=self.last_attempt_stop_reason,
            )
        )
        if self.checkpoint_hash and self.checkpoint_hash != expected:
            raise MaterialGeometricArcLengthError("checkpoint_hash mismatch")
        if not self.checkpoint_hash:
            object.__setattr__(self, "checkpoint_hash", expected)

    def to_dict(self) -> dict[str, Any]:
        return {
            **_checkpoint_payload(
                source_problem_contract_hash=self.source_problem_contract_hash,
                path_contract_hash=self.path_contract_hash,
                accepted_state=self.accepted_state,
                current_arc_length_m=self.current_arc_length_m,
                previous_tangent_displacements=(self.previous_tangent_displacements),
                previous_tangent_load_factor=self.previous_tangent_load_factor,
                attempt_count=self.attempt_count,
                last_attempt_outcome=self.last_attempt_outcome,
                last_attempt_stop_reason=self.last_attempt_stop_reason,
            ),
            "accepted_state": self.accepted_state.to_dict(),
            "checkpoint_hash": self.checkpoint_hash,
        }


def _create_checkpoint(
    *,
    source_problem_contract_hash: str,
    path_contract_hash: str,
    accepted_state: StatefulTwoBarTrussAcceptedState,
    current_arc_length_m: float,
    previous_tangent_displacements: tuple[float, float] | None,
    previous_tangent_load_factor: float | None,
    attempt_count: int,
    last_attempt_outcome: str,
    last_attempt_stop_reason: str,
) -> MaterialGeometricArcLengthCheckpoint:
    return MaterialGeometricArcLengthCheckpoint(
        source_problem_contract_hash=source_problem_contract_hash,
        path_contract_hash=path_contract_hash,
        accepted_state=accepted_state,
        current_arc_length_m=current_arc_length_m,
        previous_tangent_displacements=previous_tangent_displacements,
        previous_tangent_load_factor=previous_tangent_load_factor,
        attempt_count=attempt_count,
        last_attempt_outcome=last_attempt_outcome,
        last_attempt_stop_reason=last_attempt_stop_reason,
    )


def validate_material_geometric_arc_length_checkpoint(
    checkpoint: MaterialGeometricArcLengthCheckpoint,
    problem: StatefulTwoBarTrussProblem,
    config: VectorArcLengthConfig,
    *,
    state_tangent_solver: VectorArcLengthStateTangentSolver | None = None,
) -> MaterialGeometricArcLengthCheckpoint:
    if type(checkpoint) is not MaterialGeometricArcLengthCheckpoint:
        raise MaterialGeometricArcLengthError("checkpoint type is invalid")
    problem.validate_state(checkpoint.accepted_state)
    source_hash = _source_problem_contract_hash(problem)
    path_hash = build_material_geometric_arc_length_path_contract_hash(
        problem,
        config,
        state_tangent_solver=state_tangent_solver,
    )
    if checkpoint.source_problem_contract_hash != source_hash:
        raise MaterialGeometricArcLengthError(
            "checkpoint source problem contract mismatch"
        )
    if checkpoint.path_contract_hash != path_hash:
        raise MaterialGeometricArcLengthError("checkpoint path contract mismatch")
    if checkpoint.current_arc_length_m > config.maximum_arc_length_m:
        raise MaterialGeometricArcLengthError(
            "checkpoint arc length exceeds configured maximum"
        )
    if checkpoint.attempt_count > config.maximum_attempt_count:
        raise MaterialGeometricArcLengthError(
            "checkpoint attempt count exceeds configured maximum"
        )
    expected = _create_checkpoint(
        source_problem_contract_hash=source_hash,
        path_contract_hash=path_hash,
        accepted_state=checkpoint.accepted_state,
        current_arc_length_m=checkpoint.current_arc_length_m,
        previous_tangent_displacements=(checkpoint.previous_tangent_displacements),
        previous_tangent_load_factor=checkpoint.previous_tangent_load_factor,
        attempt_count=checkpoint.attempt_count,
        last_attempt_outcome=checkpoint.last_attempt_outcome,
        last_attempt_stop_reason=checkpoint.last_attempt_stop_reason,
    )
    if checkpoint.checkpoint_hash != expected.checkpoint_hash:
        raise MaterialGeometricArcLengthError("checkpoint_hash mismatch")
    return checkpoint


@dataclass(frozen=True)
class MaterialGeometricArcLengthAttempt:
    attempt_index: int
    arc_length_m: float
    outcome: str
    stop_reason: str
    parent_state: StatefulTwoBarTrussAcceptedState
    accepted_state: StatefulTwoBarTrussAcceptedState
    vector_result: VectorArcLengthResult
    final_assembly: StatefulTwoBarTrussAssembly | None
    rollback_exact: bool
    material_state_changed: bool
    next_arc_length_m: float
    checkpoint: MaterialGeometricArcLengthCheckpoint

    @property
    def committed(self) -> bool:
        return self.outcome == "committed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "arc_length_m": self.arc_length_m,
            "outcome": self.outcome,
            "stop_reason": self.stop_reason,
            "committed": self.committed,
            "parent_state_hash": self.parent_state.state_hash,
            "accepted_state_hash": self.accepted_state.state_hash,
            "rollback_exact": self.rollback_exact,
            "material_state_changed": self.material_state_changed,
            "next_arc_length_m": self.next_arc_length_m,
            "vector_result": _json_safe(self.vector_result.to_dict()),
            "final_assembly": (
                None if self.final_assembly is None else self.final_assembly.to_dict()
            ),
            "checkpoint": self.checkpoint.to_dict(),
        }


@dataclass(frozen=True)
class MaterialGeometricArcLengthResult:
    status: str
    terminal_reason: str
    source_case_id: str
    source_problem_contract_hash: str
    path_contract_hash: str
    profile: str
    config: VectorArcLengthConfig
    initial_checkpoint: MaterialGeometricArcLengthCheckpoint
    final_checkpoint: MaterialGeometricArcLengthCheckpoint
    checkpoints: tuple[MaterialGeometricArcLengthCheckpoint, ...]
    attempts: tuple[MaterialGeometricArcLengthAttempt, ...]
    metrics: dict[str, Any]

    @property
    def initial_state(self) -> StatefulTwoBarTrussAcceptedState:
        return self.initial_checkpoint.accepted_state

    @property
    def final_state(self) -> StatefulTwoBarTrussAcceptedState:
        return self.final_checkpoint.accepted_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MATERIAL_GEOMETRIC_ARC_LENGTH_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "profile": self.profile,
            "source_case_id": self.source_case_id,
            "source_problem_contract_hash": self.source_problem_contract_hash,
            "path_contract_hash": self.path_contract_hash,
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "tangent_action": MATERIAL_GEOMETRIC_ARC_LENGTH_TANGENT_ACTION,
            "config": asdict(self.config),
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "attempts": [row.to_dict() for row in self.attempts],
            "metrics": dict(self.metrics),
            "claims": {
                "bounded_stateful_material_geometric_arc_length": bool(
                    self.metrics["contract_pass"]
                ),
                "limit_point_and_descending_branch": bool(
                    self.metrics["descending_load_branch_observed"]
                ),
                "accepted_material_parent_rebound_each_step": bool(
                    self.metrics["accepted_step_count"] > 0
                ),
                "failed_attempt_rollback_exact": bool(
                    self.metrics["rejected_step_count"] > 0
                    and self.metrics["rollback_exact"]
                ),
                "dense_2x2_state_tangent_solves": bool(
                    self.metrics["tangent_solve_count"] > 0
                    and self.metrics["dense_2x2_state_tangent_solver"]
                ),
                "material_state_embedded_in_memory_checkpoint": True,
                "durable_serialized_checkpoint": False,
                "general_2d_3d_truss_frame_shell": False,
                "production_sparse_or_rocm_hip": False,
                "full_building_equilibrium": False,
                "g1_closure": False,
            },
            "claim_boundary": MATERIAL_GEOMETRIC_ARC_LENGTH_CLAIM_BOUNDARY,
        }


def _target_reached(
    state: StatefulTwoBarTrussAcceptedState,
    config: VectorArcLengthConfig,
) -> bool:
    monitored = state.apex_displacements_m[config.target_monitor_dof_index]
    return bool(
        config.target_direction * (monitored - config.target_monitor_displacement_m)
        >= 0.0
    )


def _single_attempt_config(
    config: VectorArcLengthConfig,
    *,
    current_arc_length_m: float,
    metric_weights: np.ndarray,
) -> VectorArcLengthConfig:
    return replace(
        config,
        target_monitor_displacement_m=math.nextafter(
            0.0,
            float(config.target_direction),
        ),
        initial_arc_length_m=current_arc_length_m,
        displacement_metric_weights=tuple(float(value) for value in metric_weights),
        maximum_attempt_count=1,
    )


def _single_vector_attempt(
    step_problem: MaterialGeometricArcLengthStepProblem,
    *,
    config: VectorArcLengthConfig,
    metric_weights: np.ndarray,
    previous_tangent_displacements: tuple[float, float] | None,
    previous_tangent_load_factor: float | None,
    solver: VectorArcLengthStateTangentSolver,
) -> VectorArcLengthResult:
    local_config = _single_attempt_config(
        config,
        current_arc_length_m=step_problem.attempt_arc_length_m,
        metric_weights=metric_weights,
    )
    local_path_hash = build_vector_arc_length_path_contract_hash(
        case_id=step_problem.case_id,
        config=local_config,
        reference_load_kn=step_problem.reference_load_kn(),
        displacement_metric_weights=metric_weights,
        tangent_solver_profile=solver.profile,
        tangent_solver_contract_hash=solver.contract_hash,
        tangent_solver_mode=VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
        equilibrium_linearization_mode=(
            VECTOR_ARC_LENGTH_LOAD_COUPLED_EQUILIBRIUM_MODE
        ),
    )
    origin = create_vector_arc_length_checkpoint(
        case_id=step_problem.case_id,
        path_contract_hash=local_path_hash,
        step_index=step_problem.accepted_state.step_index,
        free_displacements_m=np.zeros(2, dtype=np.float64),
        load_factor=0.0,
        previous_tangent_displacements=previous_tangent_displacements,
        previous_tangent_load_factor=previous_tangent_load_factor,
        current_arc_length_m=step_problem.attempt_arc_length_m,
    )
    return vector_arc_length_continuation(
        step_problem,
        config=local_config,
        resume_from=origin,
        state_tangent_solver=solver,
    )


def stateful_material_geometric_arc_length_continuation(
    problem: StatefulTwoBarTrussProblem,
    *,
    config: VectorArcLengthConfig = MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG,
    initial_state: StatefulTwoBarTrussAcceptedState | None = None,
    checkpoint: MaterialGeometricArcLengthCheckpoint | None = None,
    state_tangent_solver: VectorArcLengthStateTangentSolver | None = None,
) -> MaterialGeometricArcLengthResult:
    """Trace the bounded path with material commit/rollback per arc attempt."""

    if initial_state is not None and checkpoint is not None:
        raise MaterialGeometricArcLengthError(
            "initial_state and checkpoint are mutually exclusive"
        )
    metric_weights = _validate_config(config)
    source_hash = _source_problem_contract_hash(problem)
    solver = (
        state_tangent_solver
        or create_dense_material_geometric_state_tangent_solver(problem)
    )
    solver_profile = str(solver.profile).strip()
    if not solver_profile:
        raise MaterialGeometricArcLengthError(
            "state tangent solver profile must be non-empty"
        )
    solver_contract_hash = _require_hash(
        solver.contract_hash,
        name="state_tangent_solver.contract_hash",
    )
    default_dense_solver = bool(
        solver_profile == MATERIAL_GEOMETRIC_ARC_LENGTH_DENSE_SOLVER_PROFILE
        and solver_contract_hash == _dense_solver_contract_hash(problem)
    )
    path_profile = (
        MATERIAL_GEOMETRIC_ARC_LENGTH_PROFILE
        if default_dense_solver
        else MATERIAL_GEOMETRIC_ARC_LENGTH_EXTERNAL_SOLVER_PROFILE
    )
    path_hash = build_material_geometric_arc_length_path_contract_hash(
        problem,
        config,
        state_tangent_solver=solver,
    )
    if checkpoint is None:
        accepted = initial_state or problem.initial_state()
        problem.validate_state(accepted)
        current_arc_length_m = config.initial_arc_length_m
        previous_tangent_displacements = None
        previous_tangent_load_factor = None
        cumulative_attempt_count = 0
        initial_checkpoint = _create_checkpoint(
            source_problem_contract_hash=source_hash,
            path_contract_hash=path_hash,
            accepted_state=accepted,
            current_arc_length_m=current_arc_length_m,
            previous_tangent_displacements=None,
            previous_tangent_load_factor=None,
            attempt_count=0,
            last_attempt_outcome="initial",
            last_attempt_stop_reason="initial_equilibrium_state",
        )
        restart_consumed = False
    else:
        initial_checkpoint = validate_material_geometric_arc_length_checkpoint(
            checkpoint,
            problem,
            config,
            state_tangent_solver=solver,
        )
        accepted = initial_checkpoint.accepted_state
        current_arc_length_m = initial_checkpoint.current_arc_length_m
        previous_tangent_displacements = (
            initial_checkpoint.previous_tangent_displacements
        )
        previous_tangent_load_factor = initial_checkpoint.previous_tangent_load_factor
        cumulative_attempt_count = initial_checkpoint.attempt_count
        restart_consumed = True

    if _target_reached(accepted, config):
        raise MaterialGeometricArcLengthError(
            "initial or checkpoint state already reached the target"
        )

    checkpoints = [initial_checkpoint]
    attempts: list[MaterialGeometricArcLengthAttempt] = []
    terminal_reason = "maximum_attempt_count_exhausted"

    while cumulative_attempt_count < config.maximum_attempt_count:
        if _target_reached(accepted, config):
            terminal_reason = "target_monitor_displacement_reached"
            break
        if current_arc_length_m < config.minimum_arc_length_m:
            terminal_reason = "minimum_arc_length_exhausted"
            break
        parent = accepted
        parent_bytes = parent.canonical_bytes()
        parent_material_bytes = _material_bytes(parent)
        step_problem = MaterialGeometricArcLengthStepProblem(
            problem=problem,
            accepted_state=parent,
            attempt_arc_length_m=current_arc_length_m,
        )
        vector_result = _single_vector_attempt(
            step_problem,
            config=config,
            metric_weights=metric_weights,
            previous_tangent_displacements=previous_tangent_displacements,
            previous_tangent_load_factor=previous_tangent_load_factor,
            solver=solver,
        )
        if len(vector_result.attempts) != 1:
            raise MaterialGeometricArcLengthError(
                "single-attempt vector kernel returned an invalid count"
            )
        vector_attempt = vector_result.attempts[0]
        cumulative_attempt_count += 1
        attempted_arc_length = current_arc_length_m
        parent_unchanged = bool(
            parent.state_hash == step_problem.accepted_state.state_hash
            and parent.canonical_bytes() == parent_bytes
            and _material_bytes(parent) == parent_material_bytes
        )

        final_assembly: StatefulTwoBarTrussAssembly | None = None
        commit_gate = False
        material_state_changed = False
        if vector_attempt["accepted"] is True:
            local_final = vector_result.final_checkpoint
            final_assembly = step_problem.assemble(
                local_final.free_displacements_m,
                local_final.load_factor,
            )
            displacement_increment = np.asarray(
                local_final.free_displacements_m,
                dtype=np.float64,
            )
            load_increment = float(local_final.load_factor)
            residual_inf = float(np.linalg.norm(final_assembly.residual_kn, ord=np.inf))
            constraint_residual = float(
                np.dot(
                    metric_weights * displacement_increment,
                    displacement_increment,
                )
                + (config.load_factor_metric_scale_m * load_increment) ** 2
                - attempted_arc_length**2
            )
            monitor_increment = displacement_increment[config.target_monitor_dof_index]
            commit_gate = bool(
                vector_result.status == "ready"
                and vector_result.metrics["contract_pass"] is True
                and vector_result.metrics["fallback_count"] == 0
                and vector_result.metrics["regularization_count"] == 0
                and parent_unchanged
                and final_assembly.parent_state_hash == parent.state_hash
                and residual_inf <= config.residual_tolerance_kn
                and abs(constraint_residual) <= config.constraint_tolerance_m2
                and config.target_direction * monitor_increment > 0.0
            )

        if commit_gate:
            assert final_assembly is not None
            local_final = vector_result.final_checkpoint
            if (
                local_final.previous_tangent_displacements is None
                or local_final.previous_tangent_load_factor is None
            ):
                raise MaterialGeometricArcLengthError(
                    "accepted vector step omitted its tangent orientation"
                )
            actual_displacements = step_problem.actual_displacements_m(
                local_final.free_displacements_m
            )
            accepted = StatefulTwoBarTrussAcceptedState(
                case_id=problem.case_id,
                step_index=parent.step_index + 1,
                load_factor=step_problem.actual_load_factor(local_final.load_factor),
                apex_displacements_m=tuple(
                    float(value) for value in actual_displacements
                ),
                material_states=final_assembly.trial_material_states,
            )
            previous_tangent_displacements = tuple(
                float(value) for value in local_final.previous_tangent_displacements
            )
            previous_tangent_load_factor = float(
                local_final.previous_tangent_load_factor
            )
            material_state_changed = any(
                before.state_hash != after.state_hash
                for before, after in zip(
                    parent.material_states,
                    accepted.material_states,
                    strict=True,
                )
            )
            outcome = "committed"
            stop_reason = str(vector_attempt["stop_reason"])
            next_arc_length_m = attempted_arc_length
            rollback_exact = True
        else:
            accepted = parent
            next_arc_length_m = attempted_arc_length * config.failed_step_reduction
            current_arc_length_m = next_arc_length_m
            outcome = "rolled_back"
            stop_reason = (
                str(vector_attempt["stop_reason"])
                if vector_attempt["accepted"] is False
                else "stateful_commit_gate_failed"
            )
            rollback_exact = bool(
                parent_unchanged
                and accepted is parent
                and accepted.state_hash == parent.state_hash
                and accepted.canonical_bytes() == parent_bytes
                and _material_bytes(accepted) == parent_material_bytes
            )

        boundary = _create_checkpoint(
            source_problem_contract_hash=source_hash,
            path_contract_hash=path_hash,
            accepted_state=accepted,
            current_arc_length_m=next_arc_length_m,
            previous_tangent_displacements=previous_tangent_displacements,
            previous_tangent_load_factor=previous_tangent_load_factor,
            attempt_count=cumulative_attempt_count,
            last_attempt_outcome=outcome,
            last_attempt_stop_reason=stop_reason,
        )
        attempts.append(
            MaterialGeometricArcLengthAttempt(
                attempt_index=cumulative_attempt_count,
                arc_length_m=attempted_arc_length,
                outcome=outcome,
                stop_reason=stop_reason,
                parent_state=parent,
                accepted_state=accepted,
                vector_result=vector_result,
                final_assembly=final_assembly if commit_gate else None,
                rollback_exact=rollback_exact,
                material_state_changed=material_state_changed,
                next_arc_length_m=next_arc_length_m,
                checkpoint=boundary,
            )
        )
        checkpoints.append(boundary)
        if not commit_gate and next_arc_length_m < config.minimum_arc_length_m:
            terminal_reason = "minimum_arc_length_exhausted"
            break

    target_reached = _target_reached(accepted, config)
    if target_reached:
        terminal_reason = "target_monitor_displacement_reached"
    committed = [row for row in attempts if row.committed]
    rejected = [row for row in attempts if not row.committed]
    accepted_states = [initial_checkpoint.accepted_state] + [
        row.accepted_state for row in committed
    ]
    monitored = [state.apex_displacements_m[1] for state in accepted_states]
    load_factors = [state.load_factor for state in accepted_states]
    load_differences = [
        following - current
        for current, following in zip(load_factors, load_factors[1:])
    ]
    residual_errors = [
        float(np.linalg.norm(row.final_assembly.residual_kn, ord=np.inf))
        for row in committed
        if row.final_assembly is not None
    ]
    constraint_errors = [
        float(row.vector_result.metrics["maximum_accepted_constraint_residual_m2"])
        for row in committed
    ]
    vertical_tangents = [
        float(row.final_assembly.consistent_tangent_kn_per_m[1, 1])
        for row in committed
        if row.final_assembly is not None
    ]
    tangent_solve_count = sum(
        int(row.vector_result.metrics["external_tangent_solve_count"])
        for row in attempts
    )
    fallback_count = sum(
        int(row.vector_result.metrics["fallback_count"]) for row in attempts
    )
    regularization_count = sum(
        int(row.vector_result.metrics["regularization_count"]) for row in attempts
    )
    rollback_exact = all(row.rollback_exact for row in rejected)
    monitor_monotonic = all(
        following < current for current, following in zip(monitored, monitored[1:])
    )
    maximum_load_index = int(np.argmax(load_factors))
    descending = any(value < 0.0 for value in load_differences)
    tangent_sign_change = bool(
        vertical_tangents and min(vertical_tangents) < 0.0 < max(vertical_tangents)
    )
    coupled_terms_active = all(
        row.final_assembly is not None
        and np.linalg.norm(
            row.final_assembly.material_tangent_kn_per_m,
            ord=np.inf,
        )
        > 0.0
        and np.linalg.norm(
            row.final_assembly.geometric_tangent_kn_per_m,
            ord=np.inf,
        )
        > 0.0
        for row in committed
    )
    contract_pass = bool(
        target_reached
        and committed
        and rollback_exact
        and monitor_monotonic
        and 0 < maximum_load_index < len(load_factors) - 1
        and descending
        and tangent_sign_change
        and coupled_terms_active
        and tangent_solve_count > 0
        and fallback_count == 0
        and regularization_count == 0
        and max(residual_errors, default=math.inf) <= config.residual_tolerance_kn
        and max(constraint_errors, default=math.inf) <= config.constraint_tolerance_m2
    )
    metrics = {
        "contract_pass": contract_pass,
        "target_monitor_displacement_reached": target_reached,
        "run_attempt_count": len(attempts),
        "attempt_count": checkpoints[-1].attempt_count,
        "accepted_step_count": len(committed),
        "rejected_step_count": len(rejected),
        "failed_step_reduction_count": len(rejected),
        "rollback_exact": rollback_exact,
        "material_state_commit_rollback": bool(committed and rollback_exact),
        "material_state_changed_step_count": sum(
            int(row.material_state_changed) for row in committed
        ),
        "accepted_material_parent_rebind_count": len(committed),
        "tangent_solve_count": tangent_solve_count,
        "tangent_solver_mode": VECTOR_ARC_LENGTH_STATE_TANGENT_SOLVER_MODE,
        "tangent_solver_profile": solver_profile,
        "tangent_solver_contract_hash": solver_contract_hash,
        "dense_2x2_state_tangent_solver": default_dense_solver,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "maximum_accepted_residual_inf_norm_kn": max(
            residual_errors,
            default=None,
        ),
        "maximum_accepted_constraint_residual_m2": max(
            constraint_errors,
            default=None,
        ),
        "monitor_displacement_monotonic_downward": monitor_monotonic,
        "maximum_load_factor": max(load_factors),
        "maximum_load_step_index": maximum_load_index,
        "final_load_factor": accepted.load_factor,
        "final_monitor_displacement_m": accepted.apex_displacements_m[1],
        "descending_load_branch_observed": descending,
        "vertical_tangent_sign_change_observed": tangent_sign_change,
        "material_and_geometric_tangent_terms_active": coupled_terms_active,
        "restart_checkpoint_consumed": restart_consumed,
        "source_problem_contract_hash": source_hash,
        "path_contract_hash": path_hash,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "claim_boundary": MATERIAL_GEOMETRIC_ARC_LENGTH_CLAIM_BOUNDARY,
    }
    return MaterialGeometricArcLengthResult(
        status="ready" if contract_pass else "blocked",
        terminal_reason=terminal_reason,
        source_case_id=problem.case_id,
        source_problem_contract_hash=source_hash,
        path_contract_hash=path_hash,
        profile=path_profile,
        config=config,
        initial_checkpoint=initial_checkpoint,
        final_checkpoint=checkpoints[-1],
        checkpoints=tuple(checkpoints),
        attempts=tuple(attempts),
        metrics=metrics,
    )


def finite_difference_material_geometric_arc_length_linearization_check(
    step_problem: MaterialGeometricArcLengthStepProblem,
    *,
    displacement_increments_m: Any = (0.0, -0.012),
    increment_load_factor: float = 0.9,
    direction_m: Any = (0.3, -0.7),
    displacement_epsilon_m: float = 1.0e-7,
    load_factor_epsilon: float = 1.0e-7,
    relative_tolerance: float = 2.0e-7,
) -> dict[str, Any]:
    """Check local displacement and load derivatives from one parent."""

    displacement = _vector2(
        displacement_increments_m,
        name="displacement_increments_m",
    )
    direction = _vector2(direction_m, name="direction_m")
    if float(np.linalg.norm(direction, ord=np.inf)) <= 0.0:
        raise MaterialGeometricArcLengthError("direction_m must be nonzero")
    displacement_epsilon = _finite_scalar(
        displacement_epsilon_m,
        name="displacement_epsilon_m",
    )
    load_epsilon = _finite_scalar(
        load_factor_epsilon,
        name="load_factor_epsilon",
    )
    tolerance = _finite_scalar(
        relative_tolerance,
        name="relative_tolerance",
    )
    if displacement_epsilon <= 0.0 or load_epsilon <= 0.0 or tolerance <= 0.0:
        raise MaterialGeometricArcLengthError(
            "finite-difference controls must be positive"
        )
    load_factor = _finite_scalar(
        increment_load_factor,
        name="increment_load_factor",
    )
    parent = step_problem.accepted_state
    parent_bytes = parent.canonical_bytes()
    parent_material_bytes = _material_bytes(parent)
    analytic_displacement = step_problem.consistent_state_tangent_action_kn_per_m(
        displacement,
        load_factor,
        direction,
    )
    finite_difference_displacement = (
        step_problem.residual_kn(
            displacement + displacement_epsilon * direction,
            load_factor,
        )
        - step_problem.residual_kn(
            displacement - displacement_epsilon * direction,
            load_factor,
        )
    ) / (2.0 * displacement_epsilon)
    analytic_load = step_problem.negative_load_derivative_kn(
        displacement,
        load_factor,
    )
    finite_difference_negative_load = -(
        step_problem.residual_kn(
            displacement,
            load_factor + load_epsilon,
        )
        - step_problem.residual_kn(
            displacement,
            load_factor - load_epsilon,
        )
    ) / (2.0 * load_epsilon)
    displacement_scale = max(
        1.0,
        float(np.linalg.norm(analytic_displacement, ord=np.inf)),
        float(np.linalg.norm(finite_difference_displacement, ord=np.inf)),
    )
    load_scale = max(
        1.0,
        float(np.linalg.norm(analytic_load, ord=np.inf)),
        float(np.linalg.norm(finite_difference_negative_load, ord=np.inf)),
    )
    displacement_error = (
        float(
            np.linalg.norm(
                analytic_displacement - finite_difference_displacement,
                ord=np.inf,
            )
        )
        / displacement_scale
    )
    load_error = (
        float(
            np.linalg.norm(
                analytic_load - finite_difference_negative_load,
                ord=np.inf,
            )
        )
        / load_scale
    )
    same_parent = bool(
        parent.canonical_bytes() == parent_bytes
        and _material_bytes(parent) == parent_material_bytes
    )
    return {
        "same_committed_parent_state": same_parent,
        "displacement_jacobian_relative_inf_error": displacement_error,
        "negative_load_derivative_relative_inf_error": load_error,
        "relative_tolerance": tolerance,
        "pass": bool(
            same_parent and displacement_error <= tolerance and load_error <= tolerance
        ),
    }


def analytic_monotonic_symmetric_load_factor(
    problem: StatefulTwoBarTrussProblem,
    vertical_displacement_m: float,
) -> float:
    """Closed-form monotonic-compression branch independent of return mapping."""

    vertical = _finite_scalar(
        vertical_displacement_m,
        name="vertical_displacement_m",
    )
    if vertical > 0.0 or vertical <= -problem.rise_m:
        raise MaterialGeometricArcLengthError(
            "analytic branch requires -rise_m < vertical displacement <= 0"
        )
    current_height = problem.rise_m + vertical
    current_length = math.hypot(problem.half_span_m, current_height)
    compression_strain = (
        problem.initial_bar_length_m - current_length
    ) / problem.initial_bar_length_m
    material = problem.material
    yield_strain = material.yield_stress_mpa / material.elastic_modulus_mpa
    hardening_modulus = (
        material.isotropic_hardening_modulus_mpa
        + material.kinematic_hardening_modulus_mpa
    )
    plastic_tangent = (
        material.elastic_modulus_mpa
        * hardening_modulus
        / (material.elastic_modulus_mpa + hardening_modulus)
    )
    stress_magnitude = (
        material.elastic_modulus_mpa * compression_strain
        if compression_strain <= yield_strain
        else material.yield_stress_mpa
        + plastic_tangent * (compression_strain - yield_strain)
    )
    downward_load_kn = (
        2.0
        * problem.area_m2
        * 1000.0
        * stress_magnitude
        * current_height
        / current_length
    )
    return downward_load_kn / problem.reference_vertical_load_kn


def analytic_monotonic_limit_point(
    problem: StatefulTwoBarTrussProblem,
) -> dict[str, float]:
    """Return the unique pre-apex limit point of the closed-form branch."""

    result = minimize_scalar(
        lambda downward: (
            -analytic_monotonic_symmetric_load_factor(
                problem,
                -float(downward),
            )
        ),
        bounds=(0.0, 0.5 * problem.rise_m),
        method="bounded",
        options={"xatol": 1.0e-15},
    )
    if not result.success:
        raise MaterialGeometricArcLengthError(
            "analytic limit-point minimization failed"
        )
    displacement = -float(result.x)
    return {
        "vertical_displacement_m": displacement,
        "load_factor": analytic_monotonic_symmetric_load_factor(
            problem,
            displacement,
        ),
    }


@lru_cache(maxsize=1)
def _build_material_geometric_arc_length_benchmark_cached() -> dict[str, Any]:
    problem = StatefulTwoBarTrussProblem()
    config = MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG
    first = stateful_material_geometric_arc_length_continuation(
        problem,
        config=config,
    )
    repeated = stateful_material_geometric_arc_length_continuation(
        problem,
        config=config,
    )
    rejected_boundaries = [
        checkpoint
        for checkpoint in first.checkpoints
        if checkpoint.last_attempt_outcome == "rolled_back"
    ]
    restart_boundary = (
        rejected_boundaries[0]
        if rejected_boundaries
        else first.checkpoints[len(first.checkpoints) // 2]
    )
    restarted = stateful_material_geometric_arc_length_continuation(
        problem,
        config=config,
        checkpoint=restart_boundary,
    )
    linearization = finite_difference_material_geometric_arc_length_linearization_check(
        MaterialGeometricArcLengthStepProblem(
            problem,
            problem.initial_state(),
            config.initial_arc_length_m,
        )
    )
    committed_attempts = [row for row in first.attempts if row.committed]
    accepted_states = [first.initial_state] + [
        row.accepted_state for row in committed_attempts
    ]
    curve_rows = [
        {
            "step_index": state.step_index,
            "vertical_displacement_m": state.apex_displacements_m[1],
            "computed_load_factor": state.load_factor,
            "analytic_load_factor": analytic_monotonic_symmetric_load_factor(
                problem,
                state.apex_displacements_m[1],
            ),
        }
        for state in accepted_states
    ]
    for row in curve_rows:
        row["load_factor_abs_error"] = abs(
            row["computed_load_factor"] - row["analytic_load_factor"]
        )
    analytic_limit = analytic_monotonic_limit_point(problem)
    downward_displacements = [
        -state.apex_displacements_m[1] for state in accepted_states
    ]
    limit_downward = -analytic_limit["vertical_displacement_m"]
    bracket_index = next(
        index
        for index, (left, right) in enumerate(
            zip(downward_displacements, downward_displacements[1:])
        )
        if left <= limit_downward <= right
    )
    bracket = {
        "lower_step_index": accepted_states[bracket_index].step_index,
        "upper_step_index": accepted_states[bracket_index + 1].step_index,
        "lower_vertical_displacement_m": accepted_states[
            bracket_index
        ].apex_displacements_m[1],
        "upper_vertical_displacement_m": accepted_states[
            bracket_index + 1
        ].apex_displacements_m[1],
        "analytic_vertical_displacement_m": analytic_limit["vertical_displacement_m"],
    }
    maximum_curve_error = max(float(row["load_factor_abs_error"]) for row in curve_rows)
    deterministic_replay_exact = first.to_dict() == repeated.to_dict()
    checkpoint_restart_exact = restarted.final_checkpoint == first.final_checkpoint
    adaptive_rollback_gate = bool(
        first.metrics["rejected_step_count"] >= 1
        and first.metrics["rollback_exact"] is True
        and restart_boundary.last_attempt_outcome == "rolled_back"
        and restart_boundary.current_arc_length_m
        == config.initial_arc_length_m * config.failed_step_reduction
    )
    analytic_gate = bool(
        maximum_curve_error <= 1.0e-9
        and 0
        < first.metrics["maximum_load_step_index"]
        < first.metrics["accepted_step_count"]
        and bracket["lower_vertical_displacement_m"]
        >= analytic_limit["vertical_displacement_m"]
        >= bracket["upper_vertical_displacement_m"]
        and first.metrics["maximum_load_factor"]
        <= analytic_limit["load_factor"] + 1.0e-9
        and analytic_limit["load_factor"] - first.metrics["maximum_load_factor"]
        <= 5.0e-5
    )
    contract_pass = bool(
        first.status == "ready"
        and first.metrics["contract_pass"] is True
        and linearization["pass"] is True
        and adaptive_rollback_gate
        and deterministic_replay_exact
        and checkpoint_restart_exact
        and analytic_gate
        and first.metrics["descending_load_branch_observed"] is True
        and first.metrics["vertical_tangent_sign_change_observed"] is True
        and first.metrics["fallback_count"] == 0
        and first.metrics["regularization_count"] == 0
    )
    return {
        "schema_version": MATERIAL_GEOMETRIC_ARC_LENGTH_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": problem.case_id,
        "analysis_type": "stateful_material_geometric_vector_arc_length",
        "solver_result": first.to_dict(),
        "linearization": linearization,
        "analytic_monotonic_reference": {
            "method": (
                "closed_form_piecewise_bilinear_stress_and_exact_symmetric_"
                "current_chord_equilibrium"
            ),
            "shared_dependency": "material parameter values only",
            "limit_point": analytic_limit,
            "limit_point_bracket": bracket,
            "curve_rows": curve_rows,
            "maximum_load_factor_abs_error": maximum_curve_error,
            "sampled_maximum_load_factor_shortfall": (
                analytic_limit["load_factor"] - first.metrics["maximum_load_factor"]
            ),
            "gate_passed": analytic_gate,
        },
        "verification": {
            "deterministic_replay_exact": deterministic_replay_exact,
            "checkpoint_restart_exact": checkpoint_restart_exact,
            "restart_boundary_outcome": restart_boundary.last_attempt_outcome,
            "restart_checkpoint_hash": restart_boundary.checkpoint_hash,
            "adaptive_failed_step_rollback_gate_passed": (adaptive_rollback_gate),
            "accepted_step_count": first.metrics["accepted_step_count"],
            "rejected_step_count": first.metrics["rejected_step_count"],
            "tangent_solve_count": first.metrics["tangent_solve_count"],
            "maximum_residual_inf_norm_kn": first.metrics[
                "maximum_accepted_residual_inf_norm_kn"
            ],
            "maximum_constraint_residual_m2": first.metrics[
                "maximum_accepted_constraint_residual_m2"
            ],
            "maximum_load_factor": first.metrics["maximum_load_factor"],
            "final_load_factor": first.metrics["final_load_factor"],
            "final_vertical_displacement_m": first.metrics[
                "final_monitor_displacement_m"
            ],
            "descending_load_branch_observed": first.metrics[
                "descending_load_branch_observed"
            ],
            "vertical_tangent_sign_change_observed": first.metrics[
                "vertical_tangent_sign_change_observed"
            ],
            "material_state_changed_step_count": first.metrics[
                "material_state_changed_step_count"
            ],
            "final_dissipated_energy_density_mj_per_m3": (
                first.final_state.material_states[0].dissipated_energy_density_mj_per_m3
            ),
            "fallback_count": first.metrics["fallback_count"],
            "regularization_count": first.metrics["regularization_count"],
        },
        "verification_hierarchy": {
            "level_1_analytic": contract_pass,
            "level_2_code_to_code": False,
            "level_3_published_benchmark": False,
            "level_4_experimental": False,
            "level_5_customer_shadow": False,
        },
        "claims": {
            "bounded_stateful_material_geometric_arc_length": contract_pass,
            "limit_point_and_descending_branch": contract_pass,
            "adaptive_failed_step_rollback": contract_pass,
            "deterministic_checkpoint_restart": contract_pass,
            "closed_form_monotonic_curve_agreement": contract_pass,
            "general_2d_3d_truss_frame_shell": False,
            "finite_strain_constitutive_behavior": False,
            "durable_serialized_checkpoint": False,
            "external_code_to_code_validation": False,
            "experimental_validation": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "general_truss_frame_shell_material_geometric_adapter_missing",
            "finite_strain_constitutive_model_not_implemented",
            "checkpoint_is_in_memory_not_a_durable_artifact",
            "external_code_to_code_and_experimental_receipts_missing",
            "production_sparse_and_rocm_hip_paths_not_connected",
            "full_building_material_geometric_equilibrium_not_demonstrated",
            "g1_closure_not_claimed",
        ],
        "claim_boundary": MATERIAL_GEOMETRIC_ARC_LENGTH_CLAIM_BOUNDARY,
    }


def build_material_geometric_arc_length_benchmark() -> dict[str, Any]:
    """Return an isolated copy of the deterministic bounded benchmark."""

    return deepcopy(_build_material_geometric_arc_length_benchmark_cached())


__all__ = [
    "MATERIAL_GEOMETRIC_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION",
    "MATERIAL_GEOMETRIC_ARC_LENGTH_CLAIM_BOUNDARY",
    "MATERIAL_GEOMETRIC_ARC_LENGTH_CONFIG",
    "MATERIAL_GEOMETRIC_ARC_LENGTH_DENSE_SOLVER_PROFILE",
    "MATERIAL_GEOMETRIC_ARC_LENGTH_EXTERNAL_SOLVER_PROFILE",
    "MATERIAL_GEOMETRIC_ARC_LENGTH_PROFILE",
    "MATERIAL_GEOMETRIC_ARC_LENGTH_SCHEMA_VERSION",
    "DenseMaterialGeometricStateTangentSolver",
    "MaterialGeometricArcLengthAttempt",
    "MaterialGeometricArcLengthCheckpoint",
    "MaterialGeometricArcLengthError",
    "MaterialGeometricArcLengthResult",
    "MaterialGeometricArcLengthStepProblem",
    "analytic_monotonic_limit_point",
    "analytic_monotonic_symmetric_load_factor",
    "build_material_geometric_arc_length_benchmark",
    "build_material_geometric_arc_length_path_contract_hash",
    "build_material_geometric_source_problem_contract_hash",
    "create_dense_material_geometric_state_tangent_solver",
    "finite_difference_material_geometric_arc_length_linearization_check",
    "stateful_material_geometric_arc_length_continuation",
    "validate_material_geometric_arc_length_checkpoint",
]
