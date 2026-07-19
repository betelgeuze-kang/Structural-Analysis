"""State-updated axial-chain assembly and commit/rollback Newton load steps."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import struct
from typing import Any, Iterable, Protocol

import numpy as np

from structural_analysis.materials.bilinear_link import (
    BilinearCombinedHardeningLink,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.composite_section import (
    ParallelSteelConcreteSectionMaterial,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    SOLVE_FREE_EQUATIONS_DISPOSITION,
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
    newton_raphson_vector,
)


ACCEPTED_STATE_SCHEMA_VERSION = "stateful-axial-accepted-state.v1"
_ACCEPTED_STATE_HASH_DOMAIN = b"structural-analysis/stateful-axial-state/v1\0"
_MPA_M2_TO_KN = 1000.0


class StatefulUniaxialState(Protocol):
    state_hash: str

    def canonical_bytes(self) -> bytes: ...

    def to_dict(self) -> dict[str, Any]: ...


class StatefulUniaxialResponse(Protocol):
    stress_mpa: float
    consistent_tangent_mpa: float
    state: StatefulUniaxialState

    def to_dict(self) -> dict[str, Any]: ...


class StatefulUniaxialMaterial(Protocol):
    def initial_state(self) -> StatefulUniaxialState: ...

    def integrate(
        self,
        total_strain: float,
        committed_state: StatefulUniaxialState,
    ) -> StatefulUniaxialResponse: ...


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _require_finite(name: str, value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True)
class StatefulAxialElement:
    element_id: str
    node_i: int
    node_j: int
    length_m: float
    area_m2: float
    material: StatefulUniaxialMaterial
    response_kind: str = "stress_strain"

    def __post_init__(self) -> None:
        if not self.element_id:
            raise ValueError("element_id must be non-empty")
        if self.node_i < 0 or self.node_j < 0 or self.node_i == self.node_j:
            raise ValueError("element node indices must be distinct and non-negative")
        if _require_finite("length_m", self.length_m) <= 0.0:
            raise ValueError("length_m must be positive")
        if _require_finite("area_m2", self.area_m2) <= 0.0:
            raise ValueError("area_m2 must be positive")
        if self.response_kind not in {"stress_strain", "force_deformation"}:
            raise ValueError(
                "response_kind must be stress_strain or force_deformation"
            )


@dataclass(frozen=True)
class StatefulAxialChainProblem:
    case_id: str
    node_count: int
    elements: tuple[StatefulAxialElement, ...]
    fixed_nodes: tuple[int, ...]
    reference_external_forces_kn: tuple[tuple[int, float], ...]
    reference_prescribed_displacements_m: tuple[tuple[int, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must be non-empty")
        if self.node_count < 2:
            raise ValueError("node_count must be at least two")
        if not self.elements:
            raise ValueError("elements must be non-empty")
        if not self.fixed_nodes:
            raise ValueError("fixed_nodes must be non-empty")
        for node in self.fixed_nodes:
            if node < 0 or node >= self.node_count:
                raise ValueError("fixed node index is out of range")
        for element in self.elements:
            if element.node_i >= self.node_count or element.node_j >= self.node_count:
                raise ValueError("element node index is out of range")
        for node, force in self.reference_external_forces_kn:
            if node < 0 or node >= self.node_count:
                raise ValueError("external-force node index is out of range")
            _require_finite("reference external force", force)
        prescribed_nodes: set[int] = set()
        for node, displacement in self.reference_prescribed_displacements_m:
            if node < 0 or node >= self.node_count:
                raise ValueError("prescribed-displacement node index is out of range")
            if node in self.fixed_nodes:
                raise ValueError("a node cannot be fixed and prescribed")
            if node in prescribed_nodes:
                raise ValueError("prescribed-displacement node must be unique")
            prescribed_nodes.add(node)
            _require_finite("reference prescribed displacement", displacement)

    @property
    def free_node_indices(self) -> tuple[int, ...]:
        constrained = set(self.fixed_nodes) | {
            node for node, _ in self.reference_prescribed_displacements_m
        }
        return tuple(
            node for node in range(self.node_count) if node not in constrained
        )

    def reference_force_scale(self) -> float:
        return max(
            sum(abs(force) for _, force in self.reference_external_forces_kn),
            1.0,
        )


@dataclass(frozen=True)
class StatefulAxialAcceptedState:
    """Durable load-step state with deterministic constitutive checkpoint hash."""

    case_id: str
    step_index: int
    load_factor: float
    displacements_m: tuple[float, ...]
    material_states: tuple[StatefulUniaxialState, ...]
    state_hash: str = ""

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must be non-empty")
        if self.step_index < 0:
            raise ValueError("step_index must be non-negative")
        _require_finite("load_factor", self.load_factor)
        for displacement in self.displacements_m:
            _require_finite("displacement", displacement)
        computed = self.compute_state_hash()
        if self.state_hash and self.state_hash != computed:
            raise ValueError("accepted state hash does not match canonical state bytes")
        if not self.state_hash:
            object.__setattr__(self, "state_hash", computed)

    def canonical_bytes(self) -> bytes:
        chunks = [
            _ACCEPTED_STATE_HASH_DOMAIN,
            _pack_text(self.case_id),
            struct.pack("<QdQ", self.step_index, self.load_factor, len(self.displacements_m)),
            struct.pack(f"<{len(self.displacements_m)}d", *self.displacements_m),
            struct.pack("<Q", len(self.material_states)),
        ]
        for state in self.material_states:
            encoded = state.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    def compute_state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACCEPTED_STATE_SCHEMA_VERSION,
            "case_id": self.case_id,
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "displacements_m": list(self.displacements_m),
            "material_states": [state.to_dict() for state in self.material_states],
            "state_hash": self.state_hash,
        }


@dataclass(frozen=True)
class StatefulAxialAssemblyState:
    residual_formula: str
    target_load_factor: float
    parent_state_hash: str
    free_node_indices: tuple[int, ...]
    displacements_m: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_forces_kn: np.ndarray
    external_forces_kn: np.ndarray
    reactions_kn: np.ndarray
    element_responses: tuple[dict[str, Any], ...]
    trial_material_states: tuple[StatefulUniaxialState, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "residual_formula": self.residual_formula,
            "target_load_factor": self.target_load_factor,
            "parent_state_hash": self.parent_state_hash,
            "free_node_indices": list(self.free_node_indices),
            "displacements_m": self.displacements_m.tolist(),
            "residual_kn": self.residual_kn.tolist(),
            "jacobian_kn_per_m": self.jacobian_kn_per_m.tolist(),
            "internal_forces_kn": self.internal_forces_kn.tolist(),
            "external_forces_kn": self.external_forces_kn.tolist(),
            "reactions_kn": self.reactions_kn.tolist(),
            "element_responses": list(self.element_responses),
            "trial_material_states": [
                state.to_dict() for state in self.trial_material_states
            ],
        }


def initial_stateful_axial_state(
    problem: StatefulAxialChainProblem,
) -> StatefulAxialAcceptedState:
    return StatefulAxialAcceptedState(
        case_id=problem.case_id,
        step_index=0,
        load_factor=0.0,
        displacements_m=tuple(0.0 for _ in range(problem.node_count)),
        material_states=tuple(
            element.material.initial_state() for element in problem.elements
        ),
    )


def validate_stateful_axial_state(
    problem: StatefulAxialChainProblem,
    state: StatefulAxialAcceptedState,
) -> None:
    if state.case_id != problem.case_id:
        raise ValueError("accepted state case_id does not match problem")
    if len(state.displacements_m) != problem.node_count:
        raise ValueError("accepted displacement count does not match problem")
    if len(state.material_states) != len(problem.elements):
        raise ValueError("accepted material state count does not match problem")
    if state.compute_state_hash() != state.state_hash:
        raise ValueError("accepted state hash validation failed")


def _full_displacements(
    problem: StatefulAxialChainProblem,
    accepted_state: StatefulAxialAcceptedState,
    trial_free_displacements_m: np.ndarray,
    target_load_factor: float,
) -> np.ndarray:
    free_nodes = problem.free_node_indices
    trial = np.asarray(trial_free_displacements_m, dtype=float)
    if trial.shape != (len(free_nodes),) or not np.all(np.isfinite(trial)):
        raise ValueError("trial free displacement vector has invalid shape or values")
    full = np.asarray(accepted_state.displacements_m, dtype=float).copy()
    full[list(free_nodes)] = trial
    full[list(problem.fixed_nodes)] = 0.0
    for node, reference_displacement in problem.reference_prescribed_displacements_m:
        full[node] = reference_displacement * target_load_factor
    return full


def _external_force_vector(
    problem: StatefulAxialChainProblem,
    target_load_factor: float,
) -> np.ndarray:
    external = np.zeros(problem.node_count, dtype=float)
    for node, reference_force in problem.reference_external_forces_kn:
        external[node] += target_load_factor * reference_force
    return external


def assemble_stateful_axial_chain(
    problem: StatefulAxialChainProblem,
    accepted_state: StatefulAxialAcceptedState,
    *,
    target_load_factor: float,
    trial_free_displacements_m: np.ndarray,
) -> StatefulAxialAssemblyState:
    """Assemble a trial from one immutable accepted constitutive parent."""
    validate_stateful_axial_state(problem, accepted_state)
    load_factor = _require_finite("target_load_factor", target_load_factor)
    free_nodes = problem.free_node_indices
    node_to_free = {node: index for index, node in enumerate(free_nodes)}
    displacements = _full_displacements(
        problem,
        accepted_state,
        trial_free_displacements_m,
        load_factor,
    )
    internal = np.zeros(problem.node_count, dtype=float)
    jacobian = np.zeros((len(free_nodes), len(free_nodes)), dtype=float)
    element_rows: list[dict[str, Any]] = []
    trial_material_states: list[StatefulUniaxialState] = []

    for element_index, element in enumerate(problem.elements):
        elongation = displacements[element.node_j] - displacements[element.node_i]
        if element.response_kind == "stress_strain":
            generalized_deformation = elongation / element.length_m
            response = element.material.integrate(
                generalized_deformation,
                accepted_state.material_states[element_index],
            )
            force_kn = response.stress_mpa * element.area_m2 * _MPA_M2_TO_KN
            tangent_kn_per_m = (
                response.consistent_tangent_mpa
                * element.area_m2
                * _MPA_M2_TO_KN
                / element.length_m
            )
            total_strain: float | None = generalized_deformation
        else:
            generalized_deformation = elongation
            response = element.material.integrate(
                generalized_deformation,
                accepted_state.material_states[element_index],
            )
            force_kn = response.force_kn
            tangent_kn_per_m = response.consistent_tangent_kn_per_m
            total_strain = None
        internal[element.node_i] -= force_kn
        internal[element.node_j] += force_kn
        for node_a, sign_a in ((element.node_i, -1.0), (element.node_j, 1.0)):
            if node_a not in node_to_free:
                continue
            free_a = node_to_free[node_a]
            for node_b, sign_b in (
                (element.node_i, -1.0),
                (element.node_j, 1.0),
            ):
                if node_b not in node_to_free:
                    continue
                free_b = node_to_free[node_b]
                jacobian[free_a, free_b] += (
                    sign_a * sign_b * tangent_kn_per_m
                )
        element_rows.append(
            {
                "element_id": element.element_id,
                "node_i": element.node_i,
                "node_j": element.node_j,
                "length_m": element.length_m,
                "area_m2": element.area_m2,
                "response_kind": element.response_kind,
                "elongation_m": elongation,
                "total_strain": total_strain,
                "generalized_deformation": generalized_deformation,
                "internal_force_kn": force_kn,
                "tangent_kn_per_m": tangent_kn_per_m,
                "material_response": response.to_dict(),
            }
        )
        trial_material_states.append(response.state)

    external = _external_force_vector(problem, load_factor)
    residual = internal[list(free_nodes)] - external[list(free_nodes)]
    reactions = np.zeros(problem.node_count, dtype=float)
    constrained_nodes = set(problem.fixed_nodes) | {
        node for node, _ in problem.reference_prescribed_displacements_m
    }
    for node in constrained_nodes:
        reactions[node] = internal[node] - external[node]
    return StatefulAxialAssemblyState(
        residual_formula=RESIDUAL_FORMULA,
        target_load_factor=load_factor,
        parent_state_hash=accepted_state.state_hash,
        free_node_indices=free_nodes,
        displacements_m=displacements,
        residual_kn=residual,
        jacobian_kn_per_m=jacobian,
        internal_forces_kn=internal,
        external_forces_kn=external,
        reactions_kn=reactions,
        element_responses=tuple(element_rows),
        trial_material_states=tuple(trial_material_states),
    )


@dataclass(frozen=True)
class StatefulAxialLoadStepAdapter:
    problem: StatefulAxialChainProblem
    accepted_state: StatefulAxialAcceptedState
    target_load_factor: float

    @property
    def case_id(self) -> str:
        return f"{self.problem.case_id}@load={self.target_load_factor:.12g}"

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray(self.accepted_state.displacements_m, dtype=float)[
            list(self.problem.free_node_indices)
        ].copy()

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        state = assemble_stateful_axial_chain(
            self.problem,
            self.accepted_state,
            target_load_factor=self.target_load_factor,
            trial_free_displacements_m=free_displacements_m,
        )
        return state.residual_kn, state.jacobian_kn_per_m


@dataclass(frozen=True)
class StatefulAxialLoadStepResult:
    status: str
    committed: bool
    parent_state: StatefulAxialAcceptedState
    accepted_state: StatefulAxialAcceptedState
    trial_solution: NewtonRaphsonVectorSolution
    trial_assembly: StatefulAxialAssemblyState
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
            "trial_assembly": self.trial_assembly.to_dict(),
            "metrics": self.metrics,
        }


def solve_stateful_axial_load_step(
    problem: StatefulAxialChainProblem,
    accepted_state: StatefulAxialAcceptedState,
    *,
    target_load_factor: float,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulAxialLoadStepResult:
    """Solve one absolute load target and atomically commit or exactly rollback."""
    validate_stateful_axial_state(problem, accepted_state)
    adapter = StatefulAxialLoadStepAdapter(
        problem=problem,
        accepted_state=accepted_state,
        target_load_factor=target_load_factor,
    )
    solution = newton_raphson_vector(adapter, config=config or NewtonRaphsonConfig())
    trial_assembly = assemble_stateful_axial_chain(
        problem,
        accepted_state,
        target_load_factor=target_load_factor,
        trial_free_displacements_m=solution.free_displacements_m,
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
    solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and (no_solve_reaction_only or iterative_solver_contract)
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
    )
    if solver_contract:
        next_state = StatefulAxialAcceptedState(
            case_id=problem.case_id,
            step_index=accepted_state.step_index + 1,
            load_factor=float(target_load_factor),
            displacements_m=tuple(
                float(value) for value in trial_assembly.displacements_m
            ),
            material_states=trial_assembly.trial_material_states,
        )
        committed = True
        rollback_exact: bool | None = None
    else:
        next_state = accepted_state
        committed = False
        rollback_exact = bool(
            next_state is accepted_state
            and next_state.state_hash == accepted_state.state_hash
            and next_state.canonical_bytes() == accepted_state.canonical_bytes()
        )
    yielded_count = sum(
        bool(row["material_response"].get("yielded", False))
        for row in trial_assembly.element_responses
    )
    state_updated_count = sum(
        bool(
            row["material_response"].get("yielded", False)
            or row["material_response"].get("damage_evolved", False)
        )
        for row in trial_assembly.element_responses
    )
    return StatefulAxialLoadStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_state=accepted_state,
        accepted_state=next_state,
        trial_solution=solution,
        trial_assembly=trial_assembly,
        metrics={
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "target_load_factor": float(target_load_factor),
            "parent_state_hash": accepted_state.state_hash,
            "accepted_state_hash_after": next_state.state_hash,
            "trial_parent_state_hash": trial_assembly.parent_state_hash,
            "solver_contract_pass": solver_contract,
            "terminal_contract_pass": solver_contract,
            "iterative_solver_contract_pass": iterative_solver_contract,
            "no_solve_contract_pass": no_solve_reaction_only,
            "terminal_disposition": solution.metrics.get(
                "terminal_disposition", SOLVE_FREE_EQUATIONS_DISPOSITION
            ),
            "terminal_reason": solution.metrics.get("terminal_reason"),
            "solver_executed": bool(solution.metrics.get("solver_executed", True)),
            "active_equation_count": len(problem.free_node_indices),
            "no_solve_reaction_only": no_solve_reaction_only,
            "convergence_claim": bool(
                solution.metrics.get("convergence_claim", iterative_solver_contract)
            ),
            "residual_gate_applicable": not no_solve_reaction_only,
            "increment_gate_applicable": not no_solve_reaction_only,
            "residual_gate_passed": (
                None
                if no_solve_reaction_only
                else bool(solution.metrics.get("residual_gate_passed"))
            ),
            "increment_gate_passed": (
                None
                if no_solve_reaction_only
                else bool(solution.metrics.get("increment_gate_passed"))
            ),
            "regularization_used": bool(
                solution.metrics.get("regularization_used")
            ),
            "fallback_used": bool(solution.metrics.get("fallback_used")),
            "committed": committed,
            "rollback_exact": rollback_exact,
            "yielded_element_count": yielded_count,
            "state_updated_element_count": state_updated_count,
            "material_state_changed": bool(
                committed
                and any(
                    before.state_hash != after.state_hash
                    for before, after in zip(
                        accepted_state.material_states,
                        next_state.material_states,
                        strict=True,
                    )
                )
            ),
        },
    )


@dataclass(frozen=True)
class StatefulAxialLoadPathResult:
    status: str
    initial_state: StatefulAxialAcceptedState
    final_state: StatefulAxialAcceptedState
    steps: tuple[StatefulAxialLoadStepResult, ...] = field(default_factory=tuple)

    @property
    def contract_pass(self) -> bool:
        return bool(self.steps and all(step.committed for step in self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract_pass": self.contract_pass,
            "initial_state": self.initial_state.to_dict(),
            "final_state": self.final_state.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
        }


def run_stateful_axial_load_path(
    problem: StatefulAxialChainProblem,
    load_factors: Iterable[float],
    *,
    initial_state: StatefulAxialAcceptedState | None = None,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulAxialLoadPathResult:
    factors = tuple(_require_finite("load_factor", value) for value in load_factors)
    if not factors:
        raise ValueError("load_factors must be non-empty")
    first_state = initial_state or initial_stateful_axial_state(problem)
    validate_stateful_axial_state(problem, first_state)
    accepted = first_state
    rows: list[StatefulAxialLoadStepResult] = []
    for factor in factors:
        step = solve_stateful_axial_load_step(
            problem,
            accepted,
            target_load_factor=factor,
            config=config,
        )
        rows.append(step)
        if not step.committed:
            return StatefulAxialLoadPathResult(
                status="blocked",
                initial_state=first_state,
                final_state=accepted,
                steps=tuple(rows),
            )
        accepted = step.accepted_state
    return StatefulAxialLoadPathResult(
        status="ready",
        initial_state=first_state,
        final_state=accepted,
        steps=tuple(rows),
    )


def finite_difference_stateful_axial_jacobian_check(
    problem: StatefulAxialChainProblem,
    accepted_state: StatefulAxialAcceptedState,
    *,
    target_load_factor: float,
    trial_free_displacements_m: np.ndarray,
    epsilon: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    if epsilon <= 0.0 or not math.isfinite(epsilon):
        raise ValueError("epsilon must be finite and positive")
    base = assemble_stateful_axial_chain(
        problem,
        accepted_state,
        target_load_factor=target_load_factor,
        trial_free_displacements_m=trial_free_displacements_m,
    )
    analytic = base.jacobian_kn_per_m
    finite_difference = np.zeros_like(analytic)
    for index in range(len(problem.free_node_indices)):
        forward = np.asarray(trial_free_displacements_m, dtype=float).copy()
        backward = np.asarray(trial_free_displacements_m, dtype=float).copy()
        forward[index] += epsilon
        backward[index] -= epsilon
        residual_forward = assemble_stateful_axial_chain(
            problem,
            accepted_state,
            target_load_factor=target_load_factor,
            trial_free_displacements_m=forward,
        ).residual_kn
        residual_backward = assemble_stateful_axial_chain(
            problem,
            accepted_state,
            target_load_factor=target_load_factor,
            trial_free_displacements_m=backward,
        ).residual_kn
        finite_difference[:, index] = (
            residual_forward - residual_backward
        ) / (2.0 * epsilon)
    absolute_error = float(np.max(np.abs(finite_difference - analytic)))
    scale = max(
        float(np.max(np.abs(finite_difference))),
        float(np.max(np.abs(analytic))),
        1.0,
    )
    relative_error = absolute_error / scale
    return {
        "parent_state_hash": accepted_state.state_hash,
        "same_committed_parent_state": base.parent_state_hash
        == accepted_state.state_hash,
        "finite_difference_epsilon": epsilon,
        "analytic_jacobian_kn_per_m": analytic.tolist(),
        "finite_difference_jacobian_kn_per_m": finite_difference.tolist(),
        "max_abs_error_kn_per_m": absolute_error,
        "relative_error": relative_error,
        "relative_tolerance": relative_tolerance,
        "pass": bool(relative_error <= relative_tolerance),
    }


def single_element_stateful_steel_bar_problem(
    *,
    material: BilinearCombinedHardeningSteel | None = None,
    reference_force_kn: float = 3_000.0,
) -> StatefulAxialChainProblem:
    steel = material or BilinearCombinedHardeningSteel()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_steel_single_bar",
        node_count=2,
        elements=(
            StatefulAxialElement(
                element_id="bar-1",
                node_i=0,
                node_j=1,
                length_m=2.0,
                area_m2=0.01,
                material=steel,
            ),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=((1, reference_force_kn),),
    )


def two_element_stateful_steel_chain_problem(
    *,
    material: BilinearCombinedHardeningSteel | None = None,
    reference_force_kn: float = 3_000.0,
) -> StatefulAxialChainProblem:
    steel = material or BilinearCombinedHardeningSteel()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_steel_two_element_chain",
        node_count=3,
        elements=(
            StatefulAxialElement("bar-1", 0, 1, 1.0, 0.01, steel),
            StatefulAxialElement("bar-2", 1, 2, 1.0, 0.01, steel),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=((2, reference_force_kn),),
    )


def single_element_concrete_damage_bar_problem(
    *,
    material: AsymmetricConcreteDamageMaterial | None = None,
    reference_end_displacement_m: float = -0.002,
) -> StatefulAxialChainProblem:
    concrete = material or AsymmetricConcreteDamageMaterial()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_concrete_damage_single_bar",
        node_count=2,
        elements=(
            StatefulAxialElement("bar-1", 0, 1, 1.0, 0.01, concrete),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=(
            (1, reference_end_displacement_m),
        ),
    )


def two_element_concrete_damage_chain_problem(
    *,
    material: AsymmetricConcreteDamageMaterial | None = None,
    reference_end_displacement_m: float = -0.004,
) -> StatefulAxialChainProblem:
    concrete = material or AsymmetricConcreteDamageMaterial()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_concrete_damage_two_element_chain",
        node_count=3,
        elements=(
            StatefulAxialElement("bar-1", 0, 1, 1.0, 0.01, concrete),
            StatefulAxialElement("bar-2", 1, 2, 1.0, 0.01, concrete),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=(
            (2, reference_end_displacement_m),
        ),
    )


def single_element_composite_section_bar_problem(
    *,
    material: ParallelSteelConcreteSectionMaterial | None = None,
    reference_end_displacement_m: float = 0.002,
) -> StatefulAxialChainProblem:
    composite = material or ParallelSteelConcreteSectionMaterial()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_composite_section_single_bar",
        node_count=2,
        elements=(
            StatefulAxialElement("bar-1", 0, 1, 1.0, 0.1, composite),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=(
            (1, reference_end_displacement_m),
        ),
    )


def two_element_composite_section_chain_problem(
    *,
    material: ParallelSteelConcreteSectionMaterial | None = None,
    reference_end_displacement_m: float = 0.004,
) -> StatefulAxialChainProblem:
    composite = material or ParallelSteelConcreteSectionMaterial()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_composite_section_two_element_chain",
        node_count=3,
        elements=(
            StatefulAxialElement("bar-1", 0, 1, 1.0, 0.1, composite),
            StatefulAxialElement("bar-2", 1, 2, 1.0, 0.1, composite),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=(
            (2, reference_end_displacement_m),
        ),
    )


def single_element_bilinear_link_problem(
    *,
    material: BilinearCombinedHardeningLink | None = None,
    reference_end_displacement_m: float = 0.03,
) -> StatefulAxialChainProblem:
    link = material or BilinearCombinedHardeningLink()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_bilinear_link_single_element",
        node_count=2,
        elements=(
            StatefulAxialElement(
                "link-1",
                0,
                1,
                1.0,
                1.0,
                link,
                "force_deformation",
            ),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=(
            (1, reference_end_displacement_m),
        ),
    )


def two_element_bilinear_link_chain_problem(
    *,
    material: BilinearCombinedHardeningLink | None = None,
    reference_end_displacement_m: float = 0.06,
) -> StatefulAxialChainProblem:
    link = material or BilinearCombinedHardeningLink()
    return StatefulAxialChainProblem(
        case_id="phase2_state_updated_bilinear_link_two_element_chain",
        node_count=3,
        elements=(
            StatefulAxialElement(
                "link-1",
                0,
                1,
                1.0,
                1.0,
                link,
                "force_deformation",
            ),
            StatefulAxialElement(
                "link-2",
                1,
                2,
                1.0,
                1.0,
                link,
                "force_deformation",
            ),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=(
            (2, reference_end_displacement_m),
        ),
    )
