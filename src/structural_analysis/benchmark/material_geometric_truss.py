"""Bounded stateful material-geometric coupling benchmark.

The benchmark is a symmetric two-bar planar truss with one free apex.  Each
bar uses exact current-chord kinematics and the existing state-updated
combined-hardening steel material.  Its consistent tangent contains both the
algorithmic material term and the initial-stress geometric term.

This module is deliberately narrow: it is a Level-1 analytic verification
case, not a general corotational truss formulation or a production nonlinear
finite-element backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import struct
from typing import Any, Iterable

import numpy as np
from scipy.optimize import brentq

from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
    newton_raphson_vector,
)


MATERIAL_GEOMETRIC_TRUSS_SCHEMA_VERSION = (
    "phase2-stateful-material-geometric-two-bar-truss.v1"
)
MATERIAL_GEOMETRIC_TRUSS_FORMULATION = (
    "exact_current_chord_engineering_strain_with_algorithmic_material_"
    "and_initial_stress_geometric_tangent"
)
MATERIAL_GEOMETRIC_TRUSS_CLAIM_BOUNDARY = (
    "This receipt verifies one planar two-bar truss with exact current-chord "
    "kinematics, state-updated one-dimensional combined-hardening steel, a "
    "same-parent consistent material-plus-geometric tangent, deterministic "
    "Newton commit/rollback, and an independent symmetric scalar reduction. "
    "It does not validate a general 2D/3D truss or frame/shell formulation, "
    "distributed plasticity, a finite-strain constitutive law, arc-length "
    "continuation through the limit point, external code-to-code or "
    "experimental agreement, sparse or ROCm/HIP execution, full-building "
    "equilibrium, or G1 closure."
)

_STATE_HASH_DOMAIN = b"structural-analysis/material-geometric-truss-state/v1\0"
_MPA_M2_TO_KN = 1000.0


def _finite_scalar(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_scalar(value: Any, *, name: str) -> float:
    result = _finite_scalar(value, name=name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _vector2(values: Any, *, name: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite two-vector") from exc
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite two-vector")
    return np.array(result, dtype=np.float64, copy=True)


def _relative_inf_error(actual: np.ndarray, reference: np.ndarray) -> float:
    scale = max(
        1.0,
        float(np.linalg.norm(actual, ord=np.inf)),
        float(np.linalg.norm(reference, ord=np.inf)),
    )
    return float(np.linalg.norm(actual - reference, ord=np.inf)) / scale


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


@dataclass(frozen=True)
class StatefulTwoBarTrussAcceptedState:
    """Immutable structural and constitutive state at one accepted step."""

    case_id: str
    step_index: int
    load_factor: float
    apex_displacements_m: tuple[float, float]
    material_states: tuple[UniaxialPlasticityState, UniaxialPlasticityState]
    state_hash: str = ""

    def __post_init__(self) -> None:
        if not str(self.case_id).strip():
            raise ValueError("case_id must be non-empty")
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, (int, np.integer))
            or self.step_index < 0
        ):
            raise ValueError("step_index must be a non-negative integer")
        _finite_scalar(self.load_factor, name="load_factor")
        if len(self.apex_displacements_m) != 2:
            raise ValueError("apex_displacements_m must contain two values")
        for value in self.apex_displacements_m:
            _finite_scalar(value, name="apex displacement")
        if len(self.material_states) != 2:
            raise ValueError("material_states must contain two integration points")
        computed = self.compute_state_hash()
        if self.state_hash and self.state_hash != computed:
            raise ValueError("state_hash does not match canonical state bytes")
        if not self.state_hash:
            object.__setattr__(self, "state_hash", computed)

    def canonical_bytes(self) -> bytes:
        chunks = [
            _STATE_HASH_DOMAIN,
            _pack_text(self.case_id),
            struct.pack(
                "<Q3dQ",
                self.step_index,
                self.load_factor,
                self.apex_displacements_m[0],
                self.apex_displacements_m[1],
                len(self.material_states),
            ),
        ]
        for state in self.material_states:
            encoded = state.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    def compute_state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "apex_displacements_m": list(self.apex_displacements_m),
            "material_states": [state.to_dict() for state in self.material_states],
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class CorotationalTrussElementResponse:
    """Current-chord response at the free end of one fixed-base bar."""

    element_id: str
    initial_length_m: float
    current_length_m: float
    current_direction: np.ndarray
    engineering_strain: float
    axial_force_kn: float
    internal_force_kn: np.ndarray
    material_tangent_kn_per_m: np.ndarray
    geometric_tangent_kn_per_m: np.ndarray
    consistent_tangent_kn_per_m: np.ndarray
    material_response: UniaxialPlasticityResponse

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "initial_length_m": self.initial_length_m,
            "current_length_m": self.current_length_m,
            "current_direction": self.current_direction.tolist(),
            "engineering_strain": self.engineering_strain,
            "axial_force_kn": self.axial_force_kn,
            "internal_force_kn": self.internal_force_kn.tolist(),
            "material_tangent_kn_per_m": (self.material_tangent_kn_per_m.tolist()),
            "geometric_tangent_kn_per_m": (self.geometric_tangent_kn_per_m.tolist()),
            "consistent_tangent_kn_per_m": (self.consistent_tangent_kn_per_m.tolist()),
            "material_response": self.material_response.to_dict(),
        }


def corotational_truss_element_response(
    *,
    element_id: str,
    base_coordinate_m: Any,
    initial_apex_coordinate_m: Any,
    apex_displacement_m: Any,
    area_m2: float,
    material: BilinearCombinedHardeningSteel,
    committed_state: UniaxialPlasticityState,
) -> CorotationalTrussElementResponse:
    """Return force and the exact material-plus-geometric apex tangent.

    With ``n`` the current unit chord, ``N`` the axial force and ``L0`` the
    reference length, the tangent is

    ``A*Et/L0 * n*n.T + N/l * (I - n*n.T)``.
    """

    normalized_id = str(element_id).strip()
    if not normalized_id:
        raise ValueError("element_id must be non-empty")
    base = _vector2(base_coordinate_m, name="base_coordinate_m")
    apex = _vector2(initial_apex_coordinate_m, name="initial_apex_coordinate_m")
    displacement = _vector2(apex_displacement_m, name="apex_displacement_m")
    area = _positive_scalar(area_m2, name="area_m2")
    initial_chord = apex - base
    initial_length = float(np.linalg.norm(initial_chord))
    if initial_length <= 0.0:
        raise ValueError("the initial bar length must be positive")
    current_chord = apex + displacement - base
    current_length = float(np.linalg.norm(current_chord))
    if current_length <= np.finfo(np.float64).eps * initial_length:
        raise ValueError("the current bar length is degenerate")

    direction = current_chord / current_length
    strain = (current_length - initial_length) / initial_length
    material_response = material.integrate(strain, committed_state)
    axial_force = material_response.stress_mpa * area * _MPA_M2_TO_KN
    direction_projector = np.outer(direction, direction)
    material_tangent = (
        material_response.consistent_tangent_mpa
        * area
        * _MPA_M2_TO_KN
        / initial_length
        * direction_projector
    )
    geometric_tangent = (
        axial_force
        / current_length
        * (np.eye(2, dtype=np.float64) - direction_projector)
    )
    consistent_tangent = material_tangent + geometric_tangent
    internal_force = axial_force * direction
    for array in (
        direction,
        internal_force,
        material_tangent,
        geometric_tangent,
        consistent_tangent,
    ):
        array.setflags(write=False)
    return CorotationalTrussElementResponse(
        element_id=normalized_id,
        initial_length_m=initial_length,
        current_length_m=current_length,
        current_direction=direction,
        engineering_strain=float(strain),
        axial_force_kn=float(axial_force),
        internal_force_kn=internal_force,
        material_tangent_kn_per_m=material_tangent,
        geometric_tangent_kn_per_m=geometric_tangent,
        consistent_tangent_kn_per_m=consistent_tangent,
        material_response=material_response,
    )


@dataclass(frozen=True)
class StatefulTwoBarTrussAssembly:
    target_load_factor: float
    parent_state_hash: str
    apex_displacements_m: np.ndarray
    internal_force_kn: np.ndarray
    external_force_kn: np.ndarray
    residual_kn: np.ndarray
    material_tangent_kn_per_m: np.ndarray
    geometric_tangent_kn_per_m: np.ndarray
    consistent_tangent_kn_per_m: np.ndarray
    element_responses: tuple[
        CorotationalTrussElementResponse,
        CorotationalTrussElementResponse,
    ]
    trial_material_states: tuple[
        UniaxialPlasticityState,
        UniaxialPlasticityState,
    ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "target_load_factor": self.target_load_factor,
            "parent_state_hash": self.parent_state_hash,
            "apex_displacements_m": self.apex_displacements_m.tolist(),
            "internal_force_kn": self.internal_force_kn.tolist(),
            "external_force_kn": self.external_force_kn.tolist(),
            "residual_kn": self.residual_kn.tolist(),
            "material_tangent_kn_per_m": (self.material_tangent_kn_per_m.tolist()),
            "geometric_tangent_kn_per_m": (self.geometric_tangent_kn_per_m.tolist()),
            "consistent_tangent_kn_per_m": (self.consistent_tangent_kn_per_m.tolist()),
            "element_responses": [
                response.to_dict() for response in self.element_responses
            ],
            "trial_material_states": [
                state.to_dict() for state in self.trial_material_states
            ],
        }


@dataclass(frozen=True)
class StatefulTwoBarTrussProblem:
    """Symmetric shallow two-bar truss with a two-DOF free apex."""

    half_span_m: float = 1.0
    rise_m: float = 0.2
    area_m2: float = 0.001
    reference_vertical_load_kn: float = 100.0
    material: BilinearCombinedHardeningSteel = field(
        default_factory=BilinearCombinedHardeningSteel
    )
    case_id: str = "phase2_stateful_material_geometric_two_bar_truss"

    def __post_init__(self) -> None:
        for name in (
            "half_span_m",
            "rise_m",
            "area_m2",
            "reference_vertical_load_kn",
        ):
            object.__setattr__(
                self,
                name,
                _positive_scalar(getattr(self, name), name=name),
            )
        if not str(self.case_id).strip():
            raise ValueError("case_id must be non-empty")

    @property
    def initial_apex_coordinate_m(self) -> np.ndarray:
        result = np.asarray([0.0, self.rise_m], dtype=np.float64)
        result.setflags(write=False)
        return result

    @property
    def base_coordinates_m(self) -> tuple[np.ndarray, np.ndarray]:
        left = np.asarray([-self.half_span_m, 0.0], dtype=np.float64)
        right = np.asarray([self.half_span_m, 0.0], dtype=np.float64)
        left.setflags(write=False)
        right.setflags(write=False)
        return left, right

    @property
    def initial_bar_length_m(self) -> float:
        return math.hypot(self.half_span_m, self.rise_m)

    def reference_load_kn(self) -> np.ndarray:
        return np.asarray(
            [0.0, -self.reference_vertical_load_kn],
            dtype=np.float64,
        )

    def reference_force_scale(self) -> float:
        return self.reference_vertical_load_kn

    def initial_state(self) -> StatefulTwoBarTrussAcceptedState:
        initial_material = self.material.initial_state()
        return StatefulTwoBarTrussAcceptedState(
            case_id=self.case_id,
            step_index=0,
            load_factor=0.0,
            apex_displacements_m=(0.0, 0.0),
            material_states=(initial_material, initial_material),
        )

    def validate_state(self, state: StatefulTwoBarTrussAcceptedState) -> None:
        if state.case_id != self.case_id:
            raise ValueError("accepted state case_id does not match problem")
        if state.compute_state_hash() != state.state_hash:
            raise ValueError("accepted state hash validation failed")

    def assemble(
        self,
        accepted_state: StatefulTwoBarTrussAcceptedState,
        *,
        target_load_factor: float,
        trial_apex_displacements_m: Any,
    ) -> StatefulTwoBarTrussAssembly:
        """Assemble one trial from the same immutable constitutive parent."""

        self.validate_state(accepted_state)
        load_factor = _finite_scalar(
            target_load_factor,
            name="target_load_factor",
        )
        displacement = _vector2(
            trial_apex_displacements_m,
            name="trial_apex_displacements_m",
        )
        responses = tuple(
            corotational_truss_element_response(
                element_id=element_id,
                base_coordinate_m=base,
                initial_apex_coordinate_m=self.initial_apex_coordinate_m,
                apex_displacement_m=displacement,
                area_m2=self.area_m2,
                material=self.material,
                committed_state=material_state,
            )
            for element_id, base, material_state in zip(
                ("left-bar", "right-bar"),
                self.base_coordinates_m,
                accepted_state.material_states,
                strict=True,
            )
        )
        internal = sum(
            (response.internal_force_kn for response in responses),
            start=np.zeros(2, dtype=np.float64),
        )
        material_tangent = sum(
            (response.material_tangent_kn_per_m for response in responses),
            start=np.zeros((2, 2), dtype=np.float64),
        )
        geometric_tangent = sum(
            (response.geometric_tangent_kn_per_m for response in responses),
            start=np.zeros((2, 2), dtype=np.float64),
        )
        tangent = material_tangent + geometric_tangent
        external = load_factor * self.reference_load_kn()
        residual = internal - external
        for array in (
            displacement,
            internal,
            material_tangent,
            geometric_tangent,
            tangent,
            external,
            residual,
        ):
            array.setflags(write=False)
        return StatefulTwoBarTrussAssembly(
            target_load_factor=load_factor,
            parent_state_hash=accepted_state.state_hash,
            apex_displacements_m=displacement,
            internal_force_kn=internal,
            external_force_kn=external,
            residual_kn=residual,
            material_tangent_kn_per_m=material_tangent,
            geometric_tangent_kn_per_m=geometric_tangent,
            consistent_tangent_kn_per_m=tangent,
            element_responses=responses,
            trial_material_states=tuple(
                response.material_response.state for response in responses
            ),
        )


@dataclass(frozen=True)
class _TwoBarLoadStepAdapter:
    problem: StatefulTwoBarTrussProblem
    accepted_state: StatefulTwoBarTrussAcceptedState
    target_load_factor: float

    @property
    def case_id(self) -> str:
        return f"{self.problem.case_id}@load={self.target_load_factor:.12g}"

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray(
            self.accepted_state.apex_displacements_m,
            dtype=np.float64,
        )

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assembly = self.problem.assemble(
            self.accepted_state,
            target_load_factor=self.target_load_factor,
            trial_apex_displacements_m=free_displacements_m,
        )
        return assembly.residual_kn, assembly.consistent_tangent_kn_per_m


@dataclass(frozen=True)
class StatefulTwoBarTrussLoadStepResult:
    status: str
    committed: bool
    parent_state: StatefulTwoBarTrussAcceptedState
    accepted_state: StatefulTwoBarTrussAcceptedState
    trial_solution: NewtonRaphsonVectorSolution
    final_assembly: StatefulTwoBarTrussAssembly
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "committed": self.committed,
            "parent_state": self.parent_state.to_dict(),
            "accepted_state": self.accepted_state.to_dict(),
            "trial_solution": {
                "status": self.trial_solution.status,
                "metrics": self.trial_solution.metrics,
                "convergence_history": self.trial_solution.convergence_history,
                "line_search_history": self.trial_solution.line_search_history,
                "unsupported_features": self.trial_solution.unsupported_features,
            },
            "final_assembly": self.final_assembly.to_dict(),
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class StatefulTwoBarTrussLoadPathResult:
    status: str
    target_load_factors: tuple[float, ...]
    initial_state: StatefulTwoBarTrussAcceptedState
    final_state: StatefulTwoBarTrussAcceptedState
    steps: tuple[StatefulTwoBarTrussLoadStepResult, ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target_load_factors": list(self.target_load_factors),
            "initial_state": self.initial_state.to_dict(),
            "final_state": self.final_state.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "metrics": self.metrics,
        }


def _default_newton_config() -> NewtonRaphsonConfig:
    return NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=40,
    )


def solve_stateful_two_bar_truss_load_step(
    problem: StatefulTwoBarTrussProblem,
    accepted_state: StatefulTwoBarTrussAcceptedState,
    *,
    target_load_factor: float,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulTwoBarTrussLoadStepResult:
    """Solve one absolute load target and atomically commit or roll back."""

    problem.validate_state(accepted_state)
    load_factor = _finite_scalar(
        target_load_factor,
        name="target_load_factor",
    )
    parent_bytes = accepted_state.canonical_bytes()
    parent_material_bytes = tuple(
        state.canonical_bytes() for state in accepted_state.material_states
    )
    cfg = config or _default_newton_config()
    adapter = _TwoBarLoadStepAdapter(problem, accepted_state, load_factor)
    solution = newton_raphson_vector(adapter, config=cfg)
    final_assembly = problem.assemble(
        accepted_state,
        target_load_factor=load_factor,
        trial_apex_displacements_m=solution.free_displacements_m,
    )
    parent_unchanged = bool(
        accepted_state.canonical_bytes() == parent_bytes
        and tuple(state.canonical_bytes() for state in accepted_state.material_states)
        == parent_material_bytes
    )
    residual_inf = float(np.linalg.norm(final_assembly.residual_kn, ord=np.inf))
    residual_limit = cfg.residual_tolerance * problem.reference_force_scale()
    commit_gate = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
        and parent_unchanged
        and final_assembly.parent_state_hash == accepted_state.state_hash
        and residual_inf <= residual_limit
    )
    if commit_gate:
        next_state = StatefulTwoBarTrussAcceptedState(
            case_id=problem.case_id,
            step_index=accepted_state.step_index + 1,
            load_factor=load_factor,
            apex_displacements_m=tuple(
                float(value) for value in final_assembly.apex_displacements_m
            ),
            material_states=final_assembly.trial_material_states,
        )
    else:
        next_state = accepted_state
    rollback_exact = (
        None
        if commit_gate
        else bool(
            next_state is accepted_state
            and next_state.state_hash == accepted_state.state_hash
            and next_state.canonical_bytes() == parent_bytes
            and tuple(state.canonical_bytes() for state in next_state.material_states)
            == parent_material_bytes
        )
    )
    material_norm = float(
        np.linalg.norm(final_assembly.material_tangent_kn_per_m, ord=np.inf)
    )
    geometric_norm = float(
        np.linalg.norm(final_assembly.geometric_tangent_kn_per_m, ord=np.inf)
    )
    decomposition_error = float(
        np.linalg.norm(
            final_assembly.consistent_tangent_kn_per_m
            - final_assembly.material_tangent_kn_per_m
            - final_assembly.geometric_tangent_kn_per_m,
            ord=np.inf,
        )
    )
    metrics = {
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "parent_state_unchanged_during_trial": parent_unchanged,
        "material_state_changed": any(
            before.state_hash != after.state_hash
            for before, after in zip(
                accepted_state.material_states,
                final_assembly.trial_material_states,
                strict=True,
            )
        ),
        "committed": commit_gate,
        "rollback_exact": rollback_exact,
        "residual_inf_norm_kn": residual_inf,
        "residual_limit_kn": residual_limit,
        "material_tangent_inf_norm_kn_per_m": material_norm,
        "geometric_tangent_inf_norm_kn_per_m": geometric_norm,
        "material_and_geometric_terms_active": bool(
            material_norm > 0.0 and geometric_norm > 0.0
        ),
        "tangent_decomposition_inf_error_kn_per_m": decomposition_error,
        "regularization_count": int(bool(solution.metrics.get("regularization_used"))),
        "fallback_count": int(bool(solution.metrics.get("fallback_used"))),
        "claim_boundary": MATERIAL_GEOMETRIC_TRUSS_CLAIM_BOUNDARY,
    }
    return StatefulTwoBarTrussLoadStepResult(
        status="ready" if commit_gate else "blocked",
        committed=commit_gate,
        parent_state=accepted_state,
        accepted_state=next_state,
        trial_solution=solution,
        final_assembly=final_assembly,
        metrics=metrics,
    )


def run_stateful_two_bar_truss_load_path(
    problem: StatefulTwoBarTrussProblem,
    target_load_factors: Iterable[float],
    *,
    initial_state: StatefulTwoBarTrussAcceptedState | None = None,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulTwoBarTrussLoadPathResult:
    """Run a deterministic ordered load path, stopping at the first rollback."""

    targets = tuple(
        _finite_scalar(value, name="target_load_factor")
        for value in target_load_factors
    )
    if not targets:
        raise ValueError("target_load_factors must be non-empty")
    initial = initial_state or problem.initial_state()
    problem.validate_state(initial)
    accepted = initial
    steps: list[StatefulTwoBarTrussLoadStepResult] = []
    for target in targets:
        step = solve_stateful_two_bar_truss_load_step(
            problem,
            accepted,
            target_load_factor=target,
            config=config,
        )
        steps.append(step)
        if not step.committed:
            break
        accepted = step.accepted_state

    committed_steps = [step for step in steps if step.committed]
    rollback_steps = [step for step in steps if not step.committed]
    regularization_count = sum(
        int(step.metrics["regularization_count"]) for step in steps
    )
    fallback_count = sum(int(step.metrics["fallback_count"]) for step in steps)
    line_search_history_entry_count = sum(
        len(step.trial_solution.line_search_history) for step in committed_steps
    )
    committed_residuals = [
        float(step.metrics["residual_inf_norm_kn"]) for step in committed_steps
    ]
    contract_pass = bool(
        len(steps) == len(targets)
        and len(committed_steps) == len(targets)
        and not rollback_steps
        and regularization_count == 0
        and fallback_count == 0
    )
    return StatefulTwoBarTrussLoadPathResult(
        status="ready" if contract_pass else "blocked",
        target_load_factors=targets,
        initial_state=initial,
        final_state=accepted,
        steps=tuple(steps),
        metrics={
            "contract_pass": contract_pass,
            "requested_step_count": len(targets),
            "committed_step_count": len(committed_steps),
            "rollback_step_count": len(rollback_steps),
            "maximum_residual_inf_norm_kn": max(committed_residuals)
            if committed_residuals
            else None,
            "backtracking_used": any(
                bool(step.trial_solution.metrics.get("line_search_used"))
                for step in committed_steps
            ),
            "line_search_history_entry_count": line_search_history_entry_count,
            "line_search_history_recorded": line_search_history_entry_count > 0,
            "material_state_changed_step_count": sum(
                int(step.metrics["material_state_changed"]) for step in committed_steps
            ),
            "regularization_count": regularization_count,
            "fallback_count": fallback_count,
        },
    )


def finite_difference_two_bar_truss_tangent_check(
    problem: StatefulTwoBarTrussProblem,
    accepted_state: StatefulTwoBarTrussAcceptedState,
    *,
    apex_displacements_m: Any = (0.0, -0.012),
    target_load_factor: float = 0.9,
    epsilon_m: float = 1.0e-7,
    relative_tolerance: float = 2.0e-7,
) -> dict[str, Any]:
    """Check the coupled structural tangent from one immutable parent."""

    displacement = _vector2(
        apex_displacements_m,
        name="apex_displacements_m",
    )
    epsilon = _positive_scalar(epsilon_m, name="epsilon_m")
    tolerance = _positive_scalar(
        relative_tolerance,
        name="relative_tolerance",
    )
    load_factor = _finite_scalar(
        target_load_factor,
        name="target_load_factor",
    )
    problem.validate_state(accepted_state)
    parent_hash = accepted_state.state_hash
    parent_bytes = accepted_state.canonical_bytes()
    center = problem.assemble(
        accepted_state,
        target_load_factor=load_factor,
        trial_apex_displacements_m=displacement,
    )
    finite_difference = np.empty((2, 2), dtype=np.float64)
    for column in range(2):
        perturbation = np.zeros(2, dtype=np.float64)
        perturbation[column] = epsilon
        forward = problem.assemble(
            accepted_state,
            target_load_factor=load_factor,
            trial_apex_displacements_m=displacement + perturbation,
        )
        backward = problem.assemble(
            accepted_state,
            target_load_factor=load_factor,
            trial_apex_displacements_m=displacement - perturbation,
        )
        finite_difference[:, column] = (forward.residual_kn - backward.residual_kn) / (
            2.0 * epsilon
        )
    full_error = _relative_inf_error(
        center.consistent_tangent_kn_per_m,
        finite_difference,
    )
    material_only_error = _relative_inf_error(
        center.material_tangent_kn_per_m,
        finite_difference,
    )
    geometric_only_error = _relative_inf_error(
        center.geometric_tangent_kn_per_m,
        finite_difference,
    )
    symmetry_error = _relative_inf_error(
        center.consistent_tangent_kn_per_m,
        center.consistent_tangent_kn_per_m.T,
    )
    same_parent = bool(
        accepted_state.state_hash == parent_hash
        and accepted_state.canonical_bytes() == parent_bytes
        and all(
            response.material_response.committed_state_hash == material_state.state_hash
            for response, material_state in zip(
                center.element_responses,
                accepted_state.material_states,
                strict=True,
            )
        )
    )
    material_norm = float(np.linalg.norm(center.material_tangent_kn_per_m, ord=np.inf))
    geometric_norm = float(
        np.linalg.norm(center.geometric_tangent_kn_per_m, ord=np.inf)
    )
    return {
        "tangent_definition": MATERIAL_GEOMETRIC_TRUSS_FORMULATION,
        "same_committed_parent_state": same_parent,
        "finite_difference_epsilon_m": epsilon,
        "relative_tolerance": tolerance,
        "analytic_consistent_tangent_kn_per_m": (
            center.consistent_tangent_kn_per_m.tolist()
        ),
        "finite_difference_tangent_kn_per_m": finite_difference.tolist(),
        "material_tangent_kn_per_m": center.material_tangent_kn_per_m.tolist(),
        "geometric_tangent_kn_per_m": (center.geometric_tangent_kn_per_m.tolist()),
        "full_tangent_relative_inf_error": full_error,
        "material_only_relative_inf_error": material_only_error,
        "geometric_only_relative_inf_error": geometric_only_error,
        "tangent_symmetry_relative_inf_error": symmetry_error,
        "material_tangent_inf_norm_kn_per_m": material_norm,
        "geometric_tangent_inf_norm_kn_per_m": geometric_norm,
        "both_tangent_terms_required": bool(
            full_error <= tolerance
            and material_only_error > 100.0 * full_error
            and geometric_only_error > 100.0 * full_error
            and material_norm > 0.0
            and geometric_norm > 0.0
        ),
        "pass": bool(
            same_parent
            and full_error <= tolerance
            and symmetry_error <= 1.0e-12
            and material_only_error > 100.0 * full_error
            and geometric_only_error > 100.0 * full_error
        ),
    }


def symmetric_scalar_equilibrium_displacement_m(
    problem: StatefulTwoBarTrussProblem,
    accepted_state: StatefulTwoBarTrussAcceptedState,
    *,
    target_load_factor: float,
    search_interval_m: tuple[float, float] = (-0.08, 0.08),
    sample_count: int = 8001,
) -> float:
    """Solve the independent one-coordinate symmetric equilibrium reduction."""

    problem.validate_state(accepted_state)
    if abs(accepted_state.apex_displacements_m[0]) > 1.0e-12:
        raise ValueError("the symmetric reduction requires zero horizontal drift")
    if (
        accepted_state.material_states[0].state_hash
        != accepted_state.material_states[1].state_hash
    ):
        raise ValueError("the symmetric reduction requires equal material states")
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, (int, np.integer))
        or sample_count < 3
    ):
        raise ValueError("sample_count must be an integer of at least three")
    lower = _finite_scalar(search_interval_m[0], name="search interval lower")
    upper = _finite_scalar(search_interval_m[1], name="search interval upper")
    if lower >= upper:
        raise ValueError("search_interval_m must be strictly increasing")
    target = _finite_scalar(target_load_factor, name="target_load_factor")
    initial_length = problem.initial_bar_length_m
    parent_material = accepted_state.material_states[0]

    def scalar_residual(vertical_displacement_m: float) -> float:
        current_height = problem.rise_m + float(vertical_displacement_m)
        current_length = math.hypot(problem.half_span_m, current_height)
        strain = (current_length - initial_length) / initial_length
        response = problem.material.integrate(strain, parent_material)
        axial_force = response.stress_mpa * problem.area_m2 * _MPA_M2_TO_KN
        internal_vertical = 2.0 * axial_force * current_height / current_length
        return internal_vertical + target * problem.reference_vertical_load_kn

    samples = np.linspace(lower, upper, int(sample_count), dtype=np.float64)
    values = [scalar_residual(float(value)) for value in samples]
    roots: list[float] = []
    zero_tolerance = 1.0e-12 * problem.reference_force_scale()
    for left, right, value_left, value_right in zip(
        samples,
        samples[1:],
        values,
        values[1:],
    ):
        if abs(value_left) <= zero_tolerance:
            roots.append(float(left))
        if value_left * value_right < 0.0:
            roots.append(
                float(
                    brentq(
                        scalar_residual,
                        float(left),
                        float(right),
                        xtol=1.0e-14,
                        rtol=4.0 * np.finfo(np.float64).eps,
                    )
                )
            )
    if abs(values[-1]) <= zero_tolerance:
        roots.append(float(samples[-1]))
    unique_roots: list[float] = []
    for root in roots:
        if not any(abs(root - previous) <= 1.0e-10 for previous in unique_roots):
            unique_roots.append(root)
    if not unique_roots:
        raise ValueError("no symmetric equilibrium root exists in the search interval")
    branch_seed = accepted_state.apex_displacements_m[1]
    return min(unique_roots, key=lambda root: abs(root - branch_seed))


def _quadratic_convergence_observation(
    solution: NewtonRaphsonVectorSolution,
) -> dict[str, Any]:
    residuals = [
        float(row["relative_residual"]) for row in solution.convergence_history
    ]
    ratios = [
        following / current**2
        for current, following in zip(residuals, residuals[1:])
        if current > 1.0e-7 and following > 1.0e-12
    ]
    maximum_ratio = max(ratios) if ratios else None
    return {
        "relative_residual_history": residuals,
        "quadratic_ratio_history": ratios,
        "quadratic_window_count": len(ratios),
        "maximum_quadratic_ratio": maximum_ratio,
        "pass": bool(
            len(ratios) >= 2 and maximum_ratio is not None and maximum_ratio <= 0.1
        ),
    }


def material_geometric_two_bar_truss_benchmark() -> dict[str, Any]:
    """Build the deterministic bounded material-geometric benchmark receipt."""

    problem = StatefulTwoBarTrussProblem()
    initial = problem.initial_state()
    tangent_check = finite_difference_two_bar_truss_tangent_check(
        problem,
        initial,
    )
    quadratic_probe = solve_stateful_two_bar_truss_load_step(
        problem,
        initial,
        target_load_factor=0.8,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-12,
            increment_tolerance=1.0e-14,
            max_iterations=30,
        ),
    )
    quadratic = _quadratic_convergence_observation(quadratic_probe.trial_solution)
    forced_rollback = solve_stateful_two_bar_truss_load_step(
        problem,
        initial,
        target_load_factor=1.2,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=0,
        ),
    )
    cyclic_targets = (
        0.2,
        0.5,
        0.8,
        0.9,
        0.94,
        0.95,
        0.951,
        0.9,
        0.7,
        0.3,
        0.0,
        -0.3,
        -0.6,
        -0.9,
        -1.0,
        0.0,
        0.8,
    )
    path = run_stateful_two_bar_truss_load_path(problem, cyclic_targets)
    reference_rows: list[dict[str, Any]] = []
    for step in path.steps:
        reference_vertical = symmetric_scalar_equilibrium_displacement_m(
            problem,
            step.parent_state,
            target_load_factor=step.final_assembly.target_load_factor,
        )
        computed_horizontal, computed_vertical = (
            step.accepted_state.apex_displacements_m
        )
        reference_rows.append(
            {
                "step_index": step.accepted_state.step_index,
                "target_load_factor": step.final_assembly.target_load_factor,
                "computed_apex_displacements_m": [
                    computed_horizontal,
                    computed_vertical,
                ],
                "symmetric_scalar_vertical_displacement_m": reference_vertical,
                "horizontal_symmetry_abs_error_m": abs(computed_horizontal),
                "vertical_displacement_abs_error_m": abs(
                    computed_vertical - reference_vertical
                ),
            }
        )

    states = [path.initial_state] + [
        step.accepted_state for step in path.steps if step.committed
    ]
    plastic_strains = [state.material_states[0].plastic_strain for state in states]
    plastic_directions = [
        1 if increment > 0.0 else -1 if increment < 0.0 else 0
        for increment in (
            following - current
            for current, following in zip(
                plastic_strains,
                plastic_strains[1:],
            )
        )
    ]
    nonzero_directions = [value for value in plastic_directions if value != 0]
    plastic_reversal_count = sum(
        current != previous
        for previous, current in zip(
            nonzero_directions,
            nonzero_directions[1:],
        )
    )
    dissipations = [
        state.material_states[0].dissipated_energy_density_mj_per_m3 for state in states
    ]
    dissipation_monotonic = all(
        following + 1.0e-15 >= current
        for current, following in zip(dissipations, dissipations[1:])
    )
    maximum_reference_error = max(
        row["vertical_displacement_abs_error_m"] for row in reference_rows
    )
    maximum_symmetry_error = max(
        row["horizontal_symmetry_abs_error_m"] for row in reference_rows
    )
    maximum_residual = float(path.metrics["maximum_residual_inf_norm_kn"])
    rollback_contract = bool(
        not forced_rollback.committed
        and forced_rollback.accepted_state is forced_rollback.parent_state
        and forced_rollback.metrics["rollback_exact"] is True
        and forced_rollback.metrics["material_state_changed"] is True
    )
    contract_pass = bool(
        tangent_check["pass"] is True
        and tangent_check["both_tangent_terms_required"] is True
        and quadratic_probe.committed
        and quadratic["pass"] is True
        and rollback_contract
        and path.metrics["contract_pass"] is True
        and path.metrics["material_state_changed_step_count"] >= 3
        and path.metrics["line_search_history_recorded"] is True
        and plastic_reversal_count >= 1
        and dissipation_monotonic
        and dissipations[-1] > 0.0
        and maximum_reference_error <= 1.0e-10
        and maximum_symmetry_error <= 1.0e-12
        and maximum_residual <= 1.0e-7
        and path.metrics["regularization_count"] == 0
        and path.metrics["fallback_count"] == 0
    )
    return {
        "schema_version": MATERIAL_GEOMETRIC_TRUSS_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case": {
            "case_id": problem.case_id,
            "verification_level": "level_1_analytic",
            "formulation": MATERIAL_GEOMETRIC_TRUSS_FORMULATION,
            "half_span_m": problem.half_span_m,
            "rise_m": problem.rise_m,
            "area_m2": problem.area_m2,
            "initial_bar_length_m": problem.initial_bar_length_m,
            "reference_vertical_load_kn": problem.reference_vertical_load_kn,
            "free_equation_count": 2,
            "integration_point_count": 2,
        },
        "material": {
            "material_id": problem.material.material_id,
            "elastic_modulus_mpa": problem.material.elastic_modulus_mpa,
            "yield_stress_mpa": problem.material.yield_stress_mpa,
            "isotropic_hardening_modulus_mpa": (
                problem.material.isotropic_hardening_modulus_mpa
            ),
            "kinematic_hardening_modulus_mpa": (
                problem.material.kinematic_hardening_modulus_mpa
            ),
            "plastic_consistent_tangent_mpa": (
                problem.material.plastic_consistent_tangent_mpa
            ),
        },
        "equations": {
            "strain": "epsilon=(current_length-reference_length)/reference_length",
            "internal_force": "f_internal=N*n",
            "material_tangent": "K_material=A*Et/L0*(n outer n)",
            "geometric_tangent": "K_geometric=N/l*(I-n outer n)",
            "residual": "R=f_internal-load_factor*f_reference",
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        },
        "tangent_consistency": tangent_check,
        "quadratic_convergence": quadratic,
        "forced_failed_step": forced_rollback.to_dict(),
        "cyclic_path": {
            "target_load_factors": list(cyclic_targets),
            "path_result": path.to_dict(),
            "plastic_flow_reversal_count": plastic_reversal_count,
            "dissipation_nonnegative_monotonic": dissipation_monotonic,
            "final_dissipated_energy_density_mj_per_m3": dissipations[-1],
        },
        "analytic_symmetric_reduction": {
            "method": (
                "scalar_vertical_equilibrium_brent_root_from_same_immutable_"
                "constitutive_parent"
            ),
            "shared_dependency": (
                "verified_uniaxial_return_mapping; spatial reduction is independent"
            ),
            "rows": reference_rows,
            "maximum_vertical_displacement_abs_error_m": maximum_reference_error,
            "maximum_horizontal_symmetry_abs_error_m": maximum_symmetry_error,
        },
        "solver_summary": {
            "maximum_residual_inf_norm_kn": maximum_residual,
            "line_search_history_entry_count": (
                path.metrics["line_search_history_entry_count"]
            ),
            "line_search_history_recorded": (
                path.metrics["line_search_history_recorded"]
            ),
            "backtracking_used": path.metrics["backtracking_used"],
            "regularization_count": path.metrics["regularization_count"],
            "fallback_count": path.metrics["fallback_count"],
            "failed_step_rollback_exact": rollback_contract,
        },
        "verification_hierarchy": {
            "level_1_analytic": contract_pass,
            "level_2_code_to_code": False,
            "level_3_published_benchmark": False,
            "level_4_experimental": False,
            "level_5_customer_shadow": False,
        },
        "claims": {
            "bounded_2d_two_bar_material_geometric_coupling": contract_pass,
            "exact_current_chord_kinematics": contract_pass,
            "algorithmic_material_and_geometric_tangent": contract_pass,
            "same_parent_finite_difference_tangent": contract_pass,
            "stateful_newton_commit_rollback": contract_pass,
            "cyclic_plastic_dissipation": contract_pass,
            "independent_symmetric_scalar_reduction": contract_pass,
            "general_2d_3d_corotational_truss": False,
            "frame_shell_material_geometric_coupling": False,
            "distributed_plasticity": False,
            "finite_strain_constitutive_model": False,
            "arc_length_limit_point_continuation": False,
            "production_sparse_or_rocm_hip": False,
            "external_code_to_code_validation": False,
            "experimental_validation": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "general_corotational_truss_and_frame_shell_integration_not_implemented",
            "finite_strain_material_model_not_implemented",
            "arc_length_material_state_path_not_connected_to_this_element",
            "external_code_to_code_and_experimental_receipts_missing",
            "production_sparse_and_rocm_hip_paths_not_connected",
            "full_building_material_geometric_equilibrium_not_demonstrated",
            "g1_closure_not_claimed",
        ],
        "claim_boundary": MATERIAL_GEOMETRIC_TRUSS_CLAIM_BOUNDARY,
    }
