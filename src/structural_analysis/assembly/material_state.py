"""State-updated material Newton seed assembly."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np

from structural_analysis.materials.admissibility import (
    MaterialAdmissibility,
    require_scalar_loading_path_admissible,
)
from structural_analysis.solvers.nonlinear.newton import (
    RESIDUAL_FORMULA,
    NewtonRaphsonConfig,
    newton_raphson_vector,
)


@dataclass(frozen=True)
class StateUpdatedBilinearMaterialProblem:
    """One-DOF elastoplastic spring with isotropic hardening return mapping."""

    case_id: str
    assembly_scope: str
    structural_component: str
    material_case_kind: str
    elastic_stiffness_kn_per_m: float
    hardening_stiffness_kn_per_m: float
    yield_force_kn: float
    external_force_kn: float
    initial_displacement_m: float
    committed_plastic_displacement_m: float
    committed_equivalent_plastic_displacement_m: float
    material_family: str = "reinforced_concrete"
    section_integration: str = "frame_fiber"
    strain_mode: str = "axial"
    state_persistence_label: str = "trial_state_to_committed_state"
    loading_domain: str = "finite_uniaxial_bilinear_isotropic_hardening"
    supports_monotonic: bool = True
    supports_unloading: bool = True
    supports_reversal: bool = True
    supports_cyclic: bool = True
    supports_tension: bool = True
    supports_compression: bool = True
    supports_multiaxial: bool = False
    supports_localization_regularization: bool = False

    def reference_force_scale(self) -> float:
        return max(abs(self.external_force_kn), 1.0)

    @property
    def admissibility(self) -> MaterialAdmissibility:
        return MaterialAdmissibility(
            loading_domain=self.loading_domain,
            supports_monotonic=self.supports_monotonic,
            supports_unloading=self.supports_unloading,
            supports_reversal=self.supports_reversal,
            supports_cyclic=self.supports_cyclic,
            supports_tension=self.supports_tension,
            supports_compression=self.supports_compression,
            supports_multiaxial=self.supports_multiaxial,
            supports_localization_regularization=(
                self.supports_localization_regularization
            ),
        )


@dataclass(frozen=True)
class StateUpdatedMaterialNewtonState:
    residual_formula: str
    free_dof_labels: tuple[str, ...]
    free_displacements_m: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_forces_kn: np.ndarray
    external_forces_kn: np.ndarray
    material_state_update: dict[str, Any]
    material_algorithm_tangent_kn_per_m: float


@dataclass(frozen=True)
class StateUpdatedFrameShellCoupledMaterialProblem:
    """Two-DOF frame/shell seed with componentwise state-updated materials."""

    case_id: str
    frame_problem: StateUpdatedBilinearMaterialProblem
    shell_problem: StateUpdatedBilinearMaterialProblem
    frame_shell_coupling_stiffness_kn_per_m: float
    external_force_kn: tuple[float, float]
    initial_free_displacements_m: tuple[float, float]

    def reference_force_scale(self) -> float:
        return max(max(abs(force) for force in self.external_force_kn), 1.0)


@dataclass(frozen=True)
class StateUpdatedFrameShellCoupledMaterialState:
    residual_formula: str
    free_dof_labels: tuple[str, str]
    free_displacements_m: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_forces_kn: np.ndarray
    external_forces_kn: np.ndarray
    frame_shell_coupling_stiffness_kn_per_m: float
    component_material_states: dict[str, dict[str, Any]]
    component_internal_forces_kn: dict[str, float]


@dataclass(frozen=True)
class StateUpdatedMaterialPathHistorySpec:
    history_id: str
    base_problem: StateUpdatedBilinearMaterialProblem
    steps: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class StateUpdatedMaterialPathHistoryStep:
    history_step_index: int
    step_kind: str
    external_force_kn: float
    problem: StateUpdatedBilinearMaterialProblem
    solution: Any
    state: StateUpdatedMaterialNewtonState
    carried_committed_state_previous: dict[str, float]
    previous_committed_state_matches_carried_state: bool


@dataclass(frozen=True)
class StateUpdatedMaterialPathHistoryResult:
    history_id: str
    steps: tuple[StateUpdatedMaterialPathHistoryStep, ...]
    committed_state_chain_pass: bool
    path_dependent_update_step_count: int


@dataclass(frozen=True)
class StateUpdatedFrameShellCoupledMaterialLoadStepSpec:
    history_id: str
    base_problem: StateUpdatedFrameShellCoupledMaterialProblem
    steps: tuple[tuple[str, tuple[float, float]], ...]


@dataclass(frozen=True)
class StateUpdatedFrameShellCoupledMaterialLoadStep:
    history_step_index: int
    step_kind: str
    external_force_kn: tuple[float, float]
    problem: StateUpdatedFrameShellCoupledMaterialProblem
    solution: Any
    state: StateUpdatedFrameShellCoupledMaterialState
    carried_component_committed_state_previous: dict[str, dict[str, float]]
    previous_component_committed_state_matches_carried_state: bool


@dataclass(frozen=True)
class StateUpdatedFrameShellCoupledMaterialLoadStepResult:
    history_id: str
    steps: tuple[StateUpdatedFrameShellCoupledMaterialLoadStep, ...]
    committed_component_state_chain_pass: bool
    path_dependent_update_step_count: int


@dataclass(frozen=True)
class StateUpdatedMaterialMeshElement:
    element_id: str
    node_i: int
    node_j: int
    material_problem: StateUpdatedBilinearMaterialProblem


@dataclass(frozen=True)
class StateUpdatedMaterialAxialChainMeshProblem:
    """Small axial-chain mesh with state-updated material per element."""

    case_id: str
    node_count: int
    elements: tuple[StateUpdatedMaterialMeshElement, ...]
    fixed_nodes: tuple[int, ...]
    external_forces_kn: tuple[tuple[int, float], ...]
    initial_displacements_m: tuple[float, ...]

    def free_node_indices(self) -> tuple[int, ...]:
        fixed = set(self.fixed_nodes)
        return tuple(index for index in range(self.node_count) if index not in fixed)

    def reference_force_scale(self) -> float:
        return max(
            max((abs(force) for _, force in self.external_forces_kn), default=0.0),
            1.0,
        )


@dataclass(frozen=True)
class StateUpdatedMaterialAxialChainMeshState:
    residual_formula: str
    free_node_indices: tuple[int, ...]
    displacements_m: np.ndarray
    free_displacements_m: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_forces_kn: np.ndarray
    external_forces_kn: np.ndarray
    element_material_states: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class StateUpdatedMaterialMeshLoadStep:
    history_step_index: int
    step_kind: str
    external_force_kn: tuple[tuple[int, float], ...]
    problem: StateUpdatedMaterialAxialChainMeshProblem
    solution: Any
    state: StateUpdatedMaterialAxialChainMeshState
    carried_element_committed_state_previous: dict[str, dict[str, float]]
    previous_element_committed_state_matches_carried_state: bool


@dataclass(frozen=True)
class StateUpdatedMaterialMeshLoadStepResult:
    history_id: str
    steps: tuple[StateUpdatedMaterialMeshLoadStep, ...]
    committed_element_state_chain_pass: bool
    path_dependent_update_step_count: int


def default_state_updated_bilinear_material_problem() -> StateUpdatedBilinearMaterialProblem:
    """Return a yielded hardening seed that requires a state update."""

    return StateUpdatedBilinearMaterialProblem(
        case_id="g1_state_updated_bilinear_material_1dof_seed",
        assembly_scope="state_updated_bilinear_material_1dof_seed",
        structural_component="frame_fiber_axial",
        material_case_kind="monotonic_tension_yield",
        elastic_stiffness_kn_per_m=200.0,
        hardening_stiffness_kn_per_m=50.0,
        yield_force_kn=40.0,
        external_force_kn=100.0,
        initial_displacement_m=0.0,
        committed_plastic_displacement_m=0.0,
        committed_equivalent_plastic_displacement_m=0.0,
        material_family="reinforced_concrete",
        section_integration="frame_fiber",
        strain_mode="axial",
    )


def default_state_updated_bilinear_material_breadth_problems() -> tuple[
    StateUpdatedBilinearMaterialProblem,
    ...,
]:
    """Return narrow path-dependent frame/shell/replay material Newton seeds."""

    base = default_state_updated_bilinear_material_problem()
    return (
        base,
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_steel_frame_fiber_yield_seed",
            assembly_scope="state_updated_steel_frame_fiber_material_1dof_seed",
            structural_component="steel_frame_fiber_axial",
            material_case_kind="monotonic_steel_tension_yield",
            elastic_stiffness_kn_per_m=210.0,
            hardening_stiffness_kn_per_m=35.0,
            yield_force_kn=65.0,
            external_force_kn=115.0,
            initial_displacement_m=0.0,
            committed_plastic_displacement_m=0.0,
            committed_equivalent_plastic_displacement_m=0.0,
            material_family="steel",
            section_integration="frame_fiber",
            strain_mode="axial",
        ),
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_steel_elastic_replay_seed",
            assembly_scope="state_updated_steel_elastic_material_1dof_seed",
            structural_component="steel_frame_fiber_axial",
            material_case_kind="elastic_only_replay",
            elastic_stiffness_kn_per_m=210.0,
            hardening_stiffness_kn_per_m=35.0,
            yield_force_kn=120.0,
            external_force_kn=60.0,
            initial_displacement_m=0.0,
            committed_plastic_displacement_m=0.0,
            committed_equivalent_plastic_displacement_m=0.0,
            material_family="steel",
            section_integration="frame_fiber",
            strain_mode="axial",
        ),
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_shell_layer_compression_seed",
            assembly_scope="state_updated_shell_layer_material_1dof_seed",
            structural_component="shell_layer_membrane",
            material_case_kind="monotonic_compression_yield",
            elastic_stiffness_kn_per_m=base.elastic_stiffness_kn_per_m,
            hardening_stiffness_kn_per_m=base.hardening_stiffness_kn_per_m,
            yield_force_kn=base.yield_force_kn,
            external_force_kn=-100.0,
            initial_displacement_m=0.0,
            committed_plastic_displacement_m=0.0,
            committed_equivalent_plastic_displacement_m=0.0,
            material_family="reinforced_concrete",
            section_integration="layered_shell",
            strain_mode="membrane",
        ),
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_shell_layer_bending_seed",
            assembly_scope="state_updated_shell_layer_bending_material_1dof_seed",
            structural_component="shell_layer_bending",
            material_case_kind="monotonic_shell_bending_yield",
            elastic_stiffness_kn_per_m=160.0,
            hardening_stiffness_kn_per_m=30.0,
            yield_force_kn=35.0,
            external_force_kn=75.0,
            initial_displacement_m=0.0,
            committed_plastic_displacement_m=0.0,
            committed_equivalent_plastic_displacement_m=0.0,
            material_family="reinforced_concrete",
            section_integration="layered_shell",
            strain_mode="bending",
        ),
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_shell_drilling_elastic_seed",
            assembly_scope="state_updated_shell_drilling_material_1dof_seed",
            structural_component="shell_drilling_stiffness",
            material_case_kind="elastic_drilling_stiffness_replay",
            elastic_stiffness_kn_per_m=8.0,
            hardening_stiffness_kn_per_m=1.0,
            yield_force_kn=4.0,
            external_force_kn=1.2,
            initial_displacement_m=0.0,
            committed_plastic_displacement_m=0.0,
            committed_equivalent_plastic_displacement_m=0.0,
            material_family="shell_equivalent_plate",
            section_integration="layered_shell",
            strain_mode="drilling",
        ),
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_composite_reloading_seed",
            assembly_scope="state_updated_composite_material_reloading_1dof_seed",
            structural_component="src_composite_axial",
            material_case_kind="plastic_reloading_from_committed_state",
            elastic_stiffness_kn_per_m=base.elastic_stiffness_kn_per_m,
            hardening_stiffness_kn_per_m=base.hardening_stiffness_kn_per_m,
            yield_force_kn=base.yield_force_kn,
            external_force_kn=140.0,
            initial_displacement_m=1.7,
            committed_plastic_displacement_m=1.2,
            committed_equivalent_plastic_displacement_m=1.2,
            material_family="src_composite",
            section_integration="composite_fiber",
            strain_mode="axial",
        ),
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_composite_unloading_replay_seed",
            assembly_scope="state_updated_composite_material_unloading_1dof_seed",
            structural_component="src_composite_axial",
            material_case_kind="elastic_unloading_from_committed_state",
            elastic_stiffness_kn_per_m=base.elastic_stiffness_kn_per_m,
            hardening_stiffness_kn_per_m=base.hardening_stiffness_kn_per_m,
            yield_force_kn=base.yield_force_kn,
            external_force_kn=20.0,
            initial_displacement_m=1.7,
            committed_plastic_displacement_m=1.2,
            committed_equivalent_plastic_displacement_m=1.2,
            material_family="src_composite",
            section_integration="composite_fiber",
            strain_mode="axial",
        ),
        StateUpdatedBilinearMaterialProblem(
            case_id="g1_state_updated_rc_reverse_compression_seed",
            assembly_scope="state_updated_rc_reverse_compression_1dof_seed",
            structural_component="rc_frame_fiber_axial",
            material_case_kind="reverse_compression_from_committed_state",
            elastic_stiffness_kn_per_m=200.0,
            hardening_stiffness_kn_per_m=50.0,
            yield_force_kn=40.0,
            external_force_kn=-120.0,
            initial_displacement_m=-0.8,
            committed_plastic_displacement_m=0.6,
            committed_equivalent_plastic_displacement_m=0.6,
            material_family="reinforced_concrete",
            section_integration="frame_fiber",
            strain_mode="axial_reverse",
        ),
    )


def assemble_state_updated_material_newton_state(
    problem: StateUpdatedBilinearMaterialProblem,
    free_displacements_m: np.ndarray,
) -> StateUpdatedMaterialNewtonState:
    """Assemble R and the consistent algorithmic tangent at a trial state."""

    displacement_m = float(np.asarray(free_displacements_m, dtype=float)[0])
    update = _return_mapping_update(problem, displacement_m)
    internal = np.array([update["internal_force_kn"]], dtype=float)
    external = np.array([problem.external_force_kn], dtype=float)
    tangent = np.array([[update["algorithmic_tangent_kn_per_m"]]], dtype=float)
    return StateUpdatedMaterialNewtonState(
        residual_formula=RESIDUAL_FORMULA,
        free_dof_labels=(f"{problem.structural_component}_ux",),
        free_displacements_m=np.array([displacement_m], dtype=float),
        residual_kn=internal - external,
        jacobian_kn_per_m=tangent,
        internal_forces_kn=internal,
        external_forces_kn=external,
        material_state_update=update,
        material_algorithm_tangent_kn_per_m=float(
            update["algorithmic_tangent_kn_per_m"]
        ),
    )


@dataclass(frozen=True)
class StateUpdatedMaterialNewtonAdapter:
    problem: StateUpdatedBilinearMaterialProblem

    @property
    def case_id(self) -> str:
        return self.problem.case_id

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.array([self.problem.initial_displacement_m], dtype=float)

    def assemble(self, free_displacements_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        state = assemble_state_updated_material_newton_state(
            self.problem,
            free_displacements_m,
        )
        return state.residual_kn, state.jacobian_kn_per_m


def solve_state_updated_material_newton(
    problem: StateUpdatedBilinearMaterialProblem,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> tuple[Any, StateUpdatedMaterialNewtonState]:
    adapter = StateUpdatedMaterialNewtonAdapter(problem=problem)
    solution = newton_raphson_vector(adapter, config=config or NewtonRaphsonConfig())
    final_state = assemble_state_updated_material_newton_state(
        problem,
        solution.free_displacements_m,
    )
    return solution, final_state


def default_state_updated_material_path_history_specs() -> tuple[
    StateUpdatedMaterialPathHistorySpec,
    ...,
]:
    """Return small unload/reverse/reload histories with carried material state."""

    rc_base = default_state_updated_bilinear_material_problem()
    shell_base = StateUpdatedBilinearMaterialProblem(
        case_id="g1_state_updated_shell_membrane_cyclic_history_base",
        assembly_scope="state_updated_shell_membrane_cyclic_history_seed",
        structural_component="shell_layer_membrane",
        material_case_kind="path_history_base",
        elastic_stiffness_kn_per_m=180.0,
        hardening_stiffness_kn_per_m=45.0,
        yield_force_kn=36.0,
        external_force_kn=0.0,
        initial_displacement_m=0.0,
        committed_plastic_displacement_m=0.0,
        committed_equivalent_plastic_displacement_m=0.0,
        material_family="reinforced_concrete",
        section_integration="layered_shell",
        strain_mode="membrane",
    )
    return (
        StateUpdatedMaterialPathHistorySpec(
            history_id="rc_frame_fiber_cyclic_reversal_history",
            base_problem=rc_base,
            steps=(
                ("step01_tension_yield", 100.0),
                ("step02_elastic_unload", 20.0),
                ("step03_reverse_compression_yield", -120.0),
                ("step04_tension_reload", 80.0),
            ),
        ),
        StateUpdatedMaterialPathHistorySpec(
            history_id="shell_membrane_cyclic_reversal_history",
            base_problem=shell_base,
            steps=(
                ("step01_membrane_tension_yield", 84.0),
                ("step02_membrane_unload", 12.0),
                ("step03_membrane_reverse_yield", -96.0),
            ),
        ),
    )


def solve_state_updated_material_path_history(
    spec: StateUpdatedMaterialPathHistorySpec,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> StateUpdatedMaterialPathHistoryResult:
    """Solve a path history while carrying committed material state forward."""

    require_scalar_loading_path_admissible(
        spec.base_problem.admissibility,
        (force for _, force in spec.steps),
        owner=spec.base_problem.case_id,
    )
    previous_displacement = float(spec.base_problem.initial_displacement_m)
    previous_committed = {
        "plastic_displacement_m": float(
            spec.base_problem.committed_plastic_displacement_m
        ),
        "equivalent_plastic_displacement_m": float(
            spec.base_problem.committed_equivalent_plastic_displacement_m
        ),
    }
    step_results: list[StateUpdatedMaterialPathHistoryStep] = []
    committed_state_chain_pass = True
    solver_config = config or NewtonRaphsonConfig()
    for step_index, (step_kind, external_force_kn) in enumerate(spec.steps, start=1):
        problem = replace(
            spec.base_problem,
            case_id=f"g1_{spec.history_id}_{step_index:02d}_{step_kind}",
            assembly_scope=f"state_updated_material_path_history_{spec.history_id}",
            material_case_kind=step_kind,
            external_force_kn=external_force_kn,
            initial_displacement_m=previous_displacement,
            committed_plastic_displacement_m=previous_committed[
                "plastic_displacement_m"
            ],
            committed_equivalent_plastic_displacement_m=previous_committed[
                "equivalent_plastic_displacement_m"
            ],
            state_persistence_label=f"{spec.history_id}:{step_kind}",
        )
        solution, state = solve_state_updated_material_newton(
            problem,
            config=solver_config,
        )
        material_update = state.material_state_update
        committed_previous = dict(material_update["committed_state_previous"])
        committed_next = dict(material_update["committed_state_next"])
        previous_matches = committed_previous == previous_committed
        committed_state_chain_pass = (
            committed_state_chain_pass
            and previous_matches
            and bool(solution.metrics.get("contract_pass"))
        )
        step_results.append(
            StateUpdatedMaterialPathHistoryStep(
                history_step_index=step_index,
                step_kind=step_kind,
                external_force_kn=float(external_force_kn),
                problem=problem,
                solution=solution,
                state=state,
                carried_committed_state_previous=dict(previous_committed),
                previous_committed_state_matches_carried_state=previous_matches,
            )
        )
        previous_displacement = float(solution.free_displacements_m[0])
        previous_committed = {
            "plastic_displacement_m": float(committed_next["plastic_displacement_m"]),
            "equivalent_plastic_displacement_m": float(
                committed_next["equivalent_plastic_displacement_m"]
            ),
        }
    return StateUpdatedMaterialPathHistoryResult(
        history_id=spec.history_id,
        steps=tuple(step_results),
        committed_state_chain_pass=committed_state_chain_pass,
        path_dependent_update_step_count=sum(
            1
            for step in step_results
            if step.state.material_state_update.get("path_dependent_state_updated")
            is True
        ),
    )


def solve_default_state_updated_material_path_histories(
    *,
    config: NewtonRaphsonConfig | None = None,
) -> tuple[StateUpdatedMaterialPathHistoryResult, ...]:
    return tuple(
        solve_state_updated_material_path_history(spec, config=config)
        for spec in default_state_updated_material_path_history_specs()
    )


def default_state_updated_frame_shell_coupled_material_problem() -> (
    StateUpdatedFrameShellCoupledMaterialProblem
):
    """Return a small frame/shell coupled state-updated material seed."""

    frame = replace(
        default_state_updated_bilinear_material_problem(),
        case_id="g1_state_updated_frame_fiber_coupled_seed",
        assembly_scope="state_updated_frame_shell_coupled_material_seed",
        material_case_kind="coupled_frame_fiber_yield",
        external_force_kn=90.0,
        state_persistence_label="frame_shell_coupled_trial_to_committed_state",
    )
    shell = StateUpdatedBilinearMaterialProblem(
        case_id="g1_state_updated_shell_layer_membrane_coupled_seed",
        assembly_scope="state_updated_frame_shell_coupled_material_seed",
        structural_component="shell_layer_membrane",
        material_case_kind="coupled_shell_membrane_yield",
        elastic_stiffness_kn_per_m=160.0,
        hardening_stiffness_kn_per_m=30.0,
        yield_force_kn=35.0,
        external_force_kn=70.0,
        initial_displacement_m=0.0,
        committed_plastic_displacement_m=0.0,
        committed_equivalent_plastic_displacement_m=0.0,
        material_family="reinforced_concrete",
        section_integration="layered_shell",
        strain_mode="membrane",
        state_persistence_label="frame_shell_coupled_trial_to_committed_state",
    )
    return StateUpdatedFrameShellCoupledMaterialProblem(
        case_id="g1_state_updated_frame_shell_coupled_material_2dof_seed",
        frame_problem=frame,
        shell_problem=shell,
        frame_shell_coupling_stiffness_kn_per_m=8.0,
        external_force_kn=(90.0, 70.0),
        initial_free_displacements_m=(0.0, 0.0),
    )


def assemble_state_updated_frame_shell_coupled_material_state(
    problem: StateUpdatedFrameShellCoupledMaterialProblem,
    free_displacements_m: np.ndarray,
) -> StateUpdatedFrameShellCoupledMaterialState:
    """Assemble coupled frame/shell R and J from state-updated materials."""

    free_displacements = np.asarray(free_displacements_m, dtype=float)
    frame_state = assemble_state_updated_material_newton_state(
        problem.frame_problem,
        np.array([float(free_displacements[0])], dtype=float),
    )
    shell_state = assemble_state_updated_material_newton_state(
        problem.shell_problem,
        np.array([float(free_displacements[1])], dtype=float),
    )
    coupling = float(problem.frame_shell_coupling_stiffness_kn_per_m)
    internal = np.array(
        [
            float(frame_state.internal_forces_kn[0]) + coupling * free_displacements[1],
            float(shell_state.internal_forces_kn[0]) + coupling * free_displacements[0],
        ],
        dtype=float,
    )
    external = np.array(problem.external_force_kn, dtype=float)
    jacobian = np.array(
        [
            [float(frame_state.jacobian_kn_per_m[0, 0]), coupling],
            [coupling, float(shell_state.jacobian_kn_per_m[0, 0])],
        ],
        dtype=float,
    )
    return StateUpdatedFrameShellCoupledMaterialState(
        residual_formula=RESIDUAL_FORMULA,
        free_dof_labels=("frame_node_ux", "shell_node_uy"),
        free_displacements_m=free_displacements,
        residual_kn=internal - external,
        jacobian_kn_per_m=jacobian,
        internal_forces_kn=internal,
        external_forces_kn=external,
        frame_shell_coupling_stiffness_kn_per_m=coupling,
        component_material_states={
            "frame": frame_state.material_state_update,
            "shell": shell_state.material_state_update,
        },
        component_internal_forces_kn={
            "frame_material": float(frame_state.internal_forces_kn[0]),
            "shell_material": float(shell_state.internal_forces_kn[0]),
            "frame_coupling_from_shell": coupling * float(free_displacements[1]),
            "shell_coupling_from_frame": coupling * float(free_displacements[0]),
        },
    )


@dataclass(frozen=True)
class StateUpdatedFrameShellCoupledMaterialNewtonAdapter:
    problem: StateUpdatedFrameShellCoupledMaterialProblem

    @property
    def case_id(self) -> str:
        return self.problem.case_id

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.array(self.problem.initial_free_displacements_m, dtype=float)

    def assemble(self, free_displacements_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        state = assemble_state_updated_frame_shell_coupled_material_state(
            self.problem,
            free_displacements_m,
        )
        return state.residual_kn, state.jacobian_kn_per_m


def solve_state_updated_frame_shell_coupled_material_newton(
    problem: StateUpdatedFrameShellCoupledMaterialProblem,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> tuple[Any, StateUpdatedFrameShellCoupledMaterialState]:
    adapter = StateUpdatedFrameShellCoupledMaterialNewtonAdapter(problem=problem)
    solution = newton_raphson_vector(adapter, config=config or NewtonRaphsonConfig())
    final_state = assemble_state_updated_frame_shell_coupled_material_state(
        problem,
        solution.free_displacements_m,
    )
    return solution, final_state


def default_state_updated_frame_shell_coupled_material_load_step_spec() -> (
    StateUpdatedFrameShellCoupledMaterialLoadStepSpec
):
    """Return a coupled frame/shell load-step history carrying material state."""

    return StateUpdatedFrameShellCoupledMaterialLoadStepSpec(
        history_id="frame_shell_coupled_material_load_step_reversal_history",
        base_problem=default_state_updated_frame_shell_coupled_material_problem(),
        steps=(
            ("step01_coupled_frame_shell_yield", (90.0, 70.0)),
            ("step02_coupled_service_unload", (28.0, 18.0)),
            ("step03_coupled_reverse_yield", (-96.0, -82.0)),
            ("step04_coupled_reload", (72.0, 56.0)),
        ),
    )


def solve_state_updated_frame_shell_coupled_material_load_step_history(
    spec: StateUpdatedFrameShellCoupledMaterialLoadStepSpec | None = None,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> StateUpdatedFrameShellCoupledMaterialLoadStepResult:
    """Solve coupled load steps while carrying frame and shell material states."""

    load_step_spec = (
        spec or default_state_updated_frame_shell_coupled_material_load_step_spec()
    )
    base = load_step_spec.base_problem
    require_scalar_loading_path_admissible(
        base.frame_problem.admissibility,
        (forces[0] for _, forces in load_step_spec.steps),
        owner=base.frame_problem.case_id,
    )
    require_scalar_loading_path_admissible(
        base.shell_problem.admissibility,
        (forces[1] for _, forces in load_step_spec.steps),
        owner=base.shell_problem.case_id,
    )
    previous_displacements = tuple(float(value) for value in base.initial_free_displacements_m)
    previous_committed = {
        "frame": _committed_state_from_problem(base.frame_problem),
        "shell": _committed_state_from_problem(base.shell_problem),
    }
    solver_config = config or NewtonRaphsonConfig()
    step_results: list[StateUpdatedFrameShellCoupledMaterialLoadStep] = []
    chain_pass = True
    for step_index, (step_kind, external_force_kn) in enumerate(
        load_step_spec.steps,
        start=1,
    ):
        frame_problem = replace(
            base.frame_problem,
            case_id=f"g1_{load_step_spec.history_id}_{step_index:02d}_{step_kind}_frame",
            assembly_scope=(
                "state_updated_frame_shell_coupled_material_load_step_history"
            ),
            material_case_kind=f"{step_kind}_frame",
            external_force_kn=float(external_force_kn[0]),
            initial_displacement_m=previous_displacements[0],
            committed_plastic_displacement_m=previous_committed["frame"][
                "plastic_displacement_m"
            ],
            committed_equivalent_plastic_displacement_m=previous_committed["frame"][
                "equivalent_plastic_displacement_m"
            ],
            state_persistence_label=f"{load_step_spec.history_id}:{step_kind}:frame",
        )
        shell_problem = replace(
            base.shell_problem,
            case_id=f"g1_{load_step_spec.history_id}_{step_index:02d}_{step_kind}_shell",
            assembly_scope=(
                "state_updated_frame_shell_coupled_material_load_step_history"
            ),
            material_case_kind=f"{step_kind}_shell",
            external_force_kn=float(external_force_kn[1]),
            initial_displacement_m=previous_displacements[1],
            committed_plastic_displacement_m=previous_committed["shell"][
                "plastic_displacement_m"
            ],
            committed_equivalent_plastic_displacement_m=previous_committed["shell"][
                "equivalent_plastic_displacement_m"
            ],
            state_persistence_label=f"{load_step_spec.history_id}:{step_kind}:shell",
        )
        problem = replace(
            base,
            case_id=f"g1_{load_step_spec.history_id}_{step_index:02d}_{step_kind}",
            frame_problem=frame_problem,
            shell_problem=shell_problem,
            external_force_kn=(
                float(external_force_kn[0]),
                float(external_force_kn[1]),
            ),
            initial_free_displacements_m=previous_displacements,
        )
        solution, state = solve_state_updated_frame_shell_coupled_material_newton(
            problem,
            config=solver_config,
        )
        component_states = dict(state.component_material_states)
        frame_previous = dict(
            component_states["frame"].get("committed_state_previous") or {}
        )
        shell_previous = dict(
            component_states["shell"].get("committed_state_previous") or {}
        )
        previous_matches = (
            _material_update_matches(
                frame_previous,
                previous_committed["frame"],
                absolute_tolerance=1.0e-10,
                relative_tolerance=1.0e-10,
            )
            and _material_update_matches(
                shell_previous,
                previous_committed["shell"],
                absolute_tolerance=1.0e-10,
                relative_tolerance=1.0e-10,
            )
        )
        chain_pass = (
            chain_pass
            and previous_matches
            and bool(solution.metrics.get("contract_pass"))
        )
        step_results.append(
            StateUpdatedFrameShellCoupledMaterialLoadStep(
                history_step_index=step_index,
                step_kind=step_kind,
                external_force_kn=(
                    float(external_force_kn[0]),
                    float(external_force_kn[1]),
                ),
                problem=problem,
                solution=solution,
                state=state,
                carried_component_committed_state_previous={
                    "frame": dict(previous_committed["frame"]),
                    "shell": dict(previous_committed["shell"]),
                },
                previous_component_committed_state_matches_carried_state=(
                    previous_matches
                ),
            )
        )
        previous_displacements = tuple(
            float(value) for value in solution.free_displacements_m
        )
        previous_committed = {
            "frame": _committed_state_from_update(component_states["frame"]),
            "shell": _committed_state_from_update(component_states["shell"]),
        }
    return StateUpdatedFrameShellCoupledMaterialLoadStepResult(
        history_id=load_step_spec.history_id,
        steps=tuple(step_results),
        committed_component_state_chain_pass=chain_pass,
        path_dependent_update_step_count=sum(
            1
            for step in step_results
            for component in ("frame", "shell")
            if step.state.component_material_states[component].get(
                "path_dependent_state_updated"
            )
            is True
        ),
    )


def default_state_updated_material_axial_chain_mesh_problem() -> (
    StateUpdatedMaterialAxialChainMeshProblem
):
    """Return a two-element material mesh with frame/shell element states."""

    base_frame = default_state_updated_bilinear_material_problem()
    frame_problem = replace(
        base_frame,
        case_id="g1_state_updated_material_mesh_frame_element",
        assembly_scope="state_updated_material_axial_chain_mesh_seed",
        structural_component="mesh_frame_fiber_axial_element",
        material_case_kind="mesh_frame_element_state_updated",
        external_force_kn=0.0,
        initial_displacement_m=0.0,
        state_persistence_label="material_mesh_element_state:frame",
    )
    shell_problem = StateUpdatedBilinearMaterialProblem(
        case_id="g1_state_updated_material_mesh_shell_element",
        assembly_scope="state_updated_material_axial_chain_mesh_seed",
        structural_component="mesh_shell_layer_membrane_element",
        material_case_kind="mesh_shell_element_state_updated",
        elastic_stiffness_kn_per_m=170.0,
        hardening_stiffness_kn_per_m=35.0,
        yield_force_kn=34.0,
        external_force_kn=0.0,
        initial_displacement_m=0.0,
        committed_plastic_displacement_m=0.0,
        committed_equivalent_plastic_displacement_m=0.0,
        material_family="reinforced_concrete",
        section_integration="layered_shell",
        strain_mode="membrane",
        state_persistence_label="material_mesh_element_state:shell",
    )
    return StateUpdatedMaterialAxialChainMeshProblem(
        case_id="g1_state_updated_material_axial_chain_mesh_2element_seed",
        node_count=3,
        elements=(
            StateUpdatedMaterialMeshElement(
                element_id="mesh_frame_fiber_element_0",
                node_i=0,
                node_j=1,
                material_problem=frame_problem,
            ),
            StateUpdatedMaterialMeshElement(
                element_id="mesh_shell_membrane_element_1",
                node_i=1,
                node_j=2,
                material_problem=shell_problem,
            ),
        ),
        fixed_nodes=(0,),
        external_forces_kn=((2, 90.0),),
        initial_displacements_m=(0.0, 0.0, 0.0),
    )


def material_mesh_problem_with_external_force(
    problem: StateUpdatedMaterialAxialChainMeshProblem,
    *,
    case_id: str,
    external_forces_kn: tuple[tuple[int, float], ...],
    initial_displacements_m: tuple[float, ...],
    element_committed_states: dict[str, dict[str, float]],
    state_persistence_label: str,
) -> StateUpdatedMaterialAxialChainMeshProblem:
    elements = []
    for element in problem.elements:
        committed = element_committed_states[element.element_id]
        material_problem = replace(
            element.material_problem,
            external_force_kn=0.0,
            initial_displacement_m=0.0,
            committed_plastic_displacement_m=committed["plastic_displacement_m"],
            committed_equivalent_plastic_displacement_m=committed[
                "equivalent_plastic_displacement_m"
            ],
            state_persistence_label=f"{state_persistence_label}:{element.element_id}",
        )
        elements.append(replace(element, material_problem=material_problem))
    return replace(
        problem,
        case_id=case_id,
        elements=tuple(elements),
        external_forces_kn=external_forces_kn,
        initial_displacements_m=initial_displacements_m,
    )


def assemble_state_updated_material_axial_chain_mesh_state(
    problem: StateUpdatedMaterialAxialChainMeshProblem,
    free_displacements_m: np.ndarray,
) -> StateUpdatedMaterialAxialChainMeshState:
    """Assemble a state-updated material mesh residual and tangent."""

    free_indices = problem.free_node_indices()
    free_displacements = np.asarray(free_displacements_m, dtype=float)
    if free_displacements.shape != (len(free_indices),):
        raise ValueError("free_displacements_m must match mesh free node count.")
    displacements = np.asarray(problem.initial_displacements_m, dtype=float).copy()
    for local_index, node_index in enumerate(free_indices):
        displacements[node_index] = free_displacements[local_index]

    internal_forces = np.zeros(problem.node_count, dtype=float)
    external_forces = np.zeros(problem.node_count, dtype=float)
    for node_index, force_kn in problem.external_forces_kn:
        external_forces[int(node_index)] += float(force_kn)
    tangent_full = np.zeros((problem.node_count, problem.node_count), dtype=float)
    element_states: list[dict[str, Any]] = []
    for element in problem.elements:
        elongation = float(displacements[element.node_j] - displacements[element.node_i])
        update = _return_mapping_update(element.material_problem, elongation)
        force = float(update["internal_force_kn"])
        tangent = float(update["algorithmic_tangent_kn_per_m"])
        internal_forces[element.node_i] -= force
        internal_forces[element.node_j] += force
        tangent_full[element.node_i, element.node_i] += tangent
        tangent_full[element.node_i, element.node_j] -= tangent
        tangent_full[element.node_j, element.node_i] -= tangent
        tangent_full[element.node_j, element.node_j] += tangent
        element_states.append(
            {
                "element_id": element.element_id,
                "node_i": element.node_i,
                "node_j": element.node_j,
                "elongation_m": elongation,
                "internal_force_kn": force,
                "algorithmic_tangent_kn_per_m": tangent,
                "material_state_update": update,
            }
        )

    residual_full = internal_forces - external_forces
    free = np.asarray(free_indices, dtype=int)
    return StateUpdatedMaterialAxialChainMeshState(
        residual_formula=RESIDUAL_FORMULA,
        free_node_indices=free_indices,
        displacements_m=displacements,
        free_displacements_m=free_displacements,
        residual_kn=residual_full[free],
        jacobian_kn_per_m=tangent_full[np.ix_(free, free)],
        internal_forces_kn=internal_forces,
        external_forces_kn=external_forces,
        element_material_states=tuple(element_states),
    )


@dataclass(frozen=True)
class StateUpdatedMaterialAxialChainMeshNewtonAdapter:
    problem: StateUpdatedMaterialAxialChainMeshProblem

    @property
    def case_id(self) -> str:
        return self.problem.case_id

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        initial = np.asarray(self.problem.initial_displacements_m, dtype=float)
        return initial[list(self.problem.free_node_indices())]

    def assemble(self, free_displacements_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        state = assemble_state_updated_material_axial_chain_mesh_state(
            self.problem,
            free_displacements_m,
        )
        return state.residual_kn, state.jacobian_kn_per_m


def solve_state_updated_material_axial_chain_mesh_newton(
    problem: StateUpdatedMaterialAxialChainMeshProblem,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> tuple[Any, StateUpdatedMaterialAxialChainMeshState]:
    adapter = StateUpdatedMaterialAxialChainMeshNewtonAdapter(problem=problem)
    solution = newton_raphson_vector(adapter, config=config or NewtonRaphsonConfig())
    final_state = assemble_state_updated_material_axial_chain_mesh_state(
        problem,
        solution.free_displacements_m,
    )
    return solution, final_state


def solve_state_updated_material_mesh_load_step_history(
    *,
    config: NewtonRaphsonConfig | None = None,
) -> StateUpdatedMaterialMeshLoadStepResult:
    """Solve a small material mesh through load steps with carried element states."""

    base_problem = default_state_updated_material_axial_chain_mesh_problem()
    steps = (
        ("step01_mesh_yield", ((2, 90.0),)),
        ("step02_mesh_service_unload", ((2, 24.0),)),
        ("step03_mesh_reverse_yield", ((2, -92.0),)),
        ("step04_mesh_reload", ((2, 72.0),)),
    )
    previous_displacements = tuple(float(value) for value in base_problem.initial_displacements_m)
    previous_committed = {
        element.element_id: _committed_state_from_problem(element.material_problem)
        for element in base_problem.elements
    }
    solver_config = config or NewtonRaphsonConfig()
    step_results: list[StateUpdatedMaterialMeshLoadStep] = []
    chain_pass = True
    for step_index, (step_kind, external_forces_kn) in enumerate(steps, start=1):
        problem = material_mesh_problem_with_external_force(
            base_problem,
            case_id=f"g1_state_updated_material_mesh_history_{step_index:02d}_{step_kind}",
            external_forces_kn=external_forces_kn,
            initial_displacements_m=previous_displacements,
            element_committed_states=previous_committed,
            state_persistence_label=(
                f"material_mesh_load_step_history:{step_kind}"
            ),
        )
        solution, state = solve_state_updated_material_axial_chain_mesh_newton(
            problem,
            config=solver_config,
        )
        current_previous = {
            row["element_id"]: dict(
                row["material_state_update"].get("committed_state_previous") or {}
            )
            for row in state.element_material_states
        }
        previous_matches = all(
            _material_update_matches(
                current_previous[element_id],
                previous_committed[element_id],
                absolute_tolerance=1.0e-10,
                relative_tolerance=1.0e-10,
            )
            for element_id in previous_committed
        )
        chain_pass = (
            chain_pass
            and previous_matches
            and bool(solution.metrics.get("contract_pass"))
        )
        step_results.append(
            StateUpdatedMaterialMeshLoadStep(
                history_step_index=step_index,
                step_kind=step_kind,
                external_force_kn=tuple(
                    (int(node), float(force)) for node, force in external_forces_kn
                ),
                problem=problem,
                solution=solution,
                state=state,
                carried_element_committed_state_previous={
                    element_id: dict(committed)
                    for element_id, committed in previous_committed.items()
                },
                previous_element_committed_state_matches_carried_state=(
                    previous_matches
                ),
            )
        )
        previous_displacements = tuple(float(value) for value in state.displacements_m)
        previous_committed = {
            row["element_id"]: _committed_state_from_update(
                dict(row["material_state_update"])
            )
            for row in state.element_material_states
        }

    return StateUpdatedMaterialMeshLoadStepResult(
        history_id="state_updated_material_axial_chain_mesh_load_step_history",
        steps=tuple(step_results),
        committed_element_state_chain_pass=chain_pass,
        path_dependent_update_step_count=sum(
            1
            for step in step_results
            for row in step.state.element_material_states
            if row["material_state_update"].get("path_dependent_state_updated")
            is True
        ),
    )


def material_state_checkpoint_payload(
    problem: StateUpdatedBilinearMaterialProblem,
    state: StateUpdatedMaterialNewtonState,
) -> dict[str, Any]:
    """Build a JSON-ready checkpoint slice for material state replay."""

    return {
        "schema_version": "g1-material-state-checkpoint.seed.v1",
        "case_id": problem.case_id,
        "problem": asdict(problem),
        "free_displacements_m": state.free_displacements_m.tolist(),
        "residual_formula": state.residual_formula,
        "residual_kn": state.residual_kn.tolist(),
        "jacobian_kn_per_m": state.jacobian_kn_per_m.tolist(),
        "internal_forces_kn": state.internal_forces_kn.tolist(),
        "external_forces_kn": state.external_forces_kn.tolist(),
        "material_state_update": state.material_state_update,
    }


def material_path_history_checkpoint_payload(
    history: StateUpdatedMaterialPathHistoryResult,
) -> dict[str, Any]:
    """Build a JSON-ready checkpoint for a carried material path history."""

    return {
        "schema_version": "g1-material-path-history-checkpoint.seed.v1",
        "history_id": history.history_id,
        "residual_formula": RESIDUAL_FORMULA,
        "step_count": len(history.steps),
        "committed_state_chain_pass": history.committed_state_chain_pass,
        "path_dependent_update_step_count": (
            history.path_dependent_update_step_count
        ),
        "steps": [
            {
                "history_step_index": step.history_step_index,
                "step_kind": step.step_kind,
                "case_id": step.problem.case_id,
                "external_force_kn": step.external_force_kn,
                "problem": asdict(step.problem),
                "free_displacements_m": step.state.free_displacements_m.tolist(),
                "residual_formula": step.state.residual_formula,
                "residual_kn": step.state.residual_kn.tolist(),
                "jacobian_kn_per_m": step.state.jacobian_kn_per_m.tolist(),
                "internal_forces_kn": step.state.internal_forces_kn.tolist(),
                "external_forces_kn": step.state.external_forces_kn.tolist(),
                "material_state_update": step.state.material_state_update,
                "carried_committed_state_previous": (
                    step.carried_committed_state_previous
                ),
                "previous_committed_state_matches_carried_state": (
                    step.previous_committed_state_matches_carried_state
                ),
            }
            for step in history.steps
        ],
    }


def frame_shell_coupled_material_load_step_checkpoint_payload(
    history: StateUpdatedFrameShellCoupledMaterialLoadStepResult,
) -> dict[str, Any]:
    """Build a JSON-ready checkpoint for coupled frame/shell load steps."""

    return {
        "schema_version": (
            "g1-frame-shell-coupled-material-load-step-checkpoint.seed.v1"
        ),
        "history_id": history.history_id,
        "residual_formula": RESIDUAL_FORMULA,
        "step_count": len(history.steps),
        "committed_component_state_chain_pass": (
            history.committed_component_state_chain_pass
        ),
        "path_dependent_update_step_count": (
            history.path_dependent_update_step_count
        ),
        "steps": [
            {
                "history_step_index": step.history_step_index,
                "step_kind": step.step_kind,
                "case_id": step.problem.case_id,
                "external_force_kn": list(step.external_force_kn),
                "problem": {
                    "case_id": step.problem.case_id,
                    "frame_problem": asdict(step.problem.frame_problem),
                    "shell_problem": asdict(step.problem.shell_problem),
                    "frame_shell_coupling_stiffness_kn_per_m": (
                        step.problem.frame_shell_coupling_stiffness_kn_per_m
                    ),
                    "external_force_kn": list(step.problem.external_force_kn),
                    "initial_free_displacements_m": list(
                        step.problem.initial_free_displacements_m
                    ),
                },
                "free_displacements_m": step.state.free_displacements_m.tolist(),
                "residual_formula": step.state.residual_formula,
                "residual_kn": step.state.residual_kn.tolist(),
                "jacobian_kn_per_m": step.state.jacobian_kn_per_m.tolist(),
                "internal_forces_kn": step.state.internal_forces_kn.tolist(),
                "external_forces_kn": step.state.external_forces_kn.tolist(),
                "frame_shell_coupling_stiffness_kn_per_m": (
                    step.state.frame_shell_coupling_stiffness_kn_per_m
                ),
                "component_material_states": step.state.component_material_states,
                "component_internal_forces_kn": (
                    step.state.component_internal_forces_kn
                ),
                "carried_component_committed_state_previous": (
                    step.carried_component_committed_state_previous
                ),
                "previous_component_committed_state_matches_carried_state": (
                    step.previous_component_committed_state_matches_carried_state
                ),
            }
            for step in history.steps
        ],
    }


def material_mesh_load_step_checkpoint_payload(
    history: StateUpdatedMaterialMeshLoadStepResult,
) -> dict[str, Any]:
    """Build a JSON-ready checkpoint for a state-updated material mesh history."""

    return {
        "schema_version": "g1-material-mesh-load-step-checkpoint.seed.v1",
        "history_id": history.history_id,
        "residual_formula": RESIDUAL_FORMULA,
        "step_count": len(history.steps),
        "committed_element_state_chain_pass": (
            history.committed_element_state_chain_pass
        ),
        "path_dependent_update_step_count": history.path_dependent_update_step_count,
        "steps": [
            {
                "history_step_index": step.history_step_index,
                "step_kind": step.step_kind,
                "case_id": step.problem.case_id,
                "external_force_kn": [
                    {"node_index": node, "force_kn": force}
                    for node, force in step.external_force_kn
                ],
                "problem": {
                    "case_id": step.problem.case_id,
                    "node_count": step.problem.node_count,
                    "fixed_nodes": list(step.problem.fixed_nodes),
                    "external_forces_kn": [
                        {"node_index": node, "force_kn": force}
                        for node, force in step.problem.external_forces_kn
                    ],
                    "initial_displacements_m": list(
                        step.problem.initial_displacements_m
                    ),
                    "elements": [
                        {
                            "element_id": element.element_id,
                            "node_i": element.node_i,
                            "node_j": element.node_j,
                            "material_problem": asdict(element.material_problem),
                        }
                        for element in step.problem.elements
                    ],
                },
                "free_node_indices": list(step.state.free_node_indices),
                "displacements_m": step.state.displacements_m.tolist(),
                "free_displacements_m": step.state.free_displacements_m.tolist(),
                "residual_formula": step.state.residual_formula,
                "residual_kn": step.state.residual_kn.tolist(),
                "jacobian_kn_per_m": step.state.jacobian_kn_per_m.tolist(),
                "internal_forces_kn": step.state.internal_forces_kn.tolist(),
                "external_forces_kn": step.state.external_forces_kn.tolist(),
                "element_material_states": list(step.state.element_material_states),
                "carried_element_committed_state_previous": (
                    step.carried_element_committed_state_previous
                ),
                "previous_element_committed_state_matches_carried_state": (
                    step.previous_element_committed_state_matches_carried_state
                ),
            }
            for step in history.steps
        ],
    }


def check_state_updated_material_checkpoint_replay(
    checkpoint: dict[str, Any],
    *,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 1.0e-10,
) -> dict[str, Any]:
    """Replay a serialized material checkpoint through the same return mapping."""

    problem = StateUpdatedBilinearMaterialProblem(**dict(checkpoint["problem"]))
    free_displacements = np.asarray(
        checkpoint["free_displacements_m"],
        dtype=float,
    )
    replay = assemble_state_updated_material_newton_state(problem, free_displacements)
    residual_replay_match = _allclose_payload(
        replay.residual_kn,
        checkpoint["residual_kn"],
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    tangent_replay_match = _allclose_payload(
        replay.jacobian_kn_per_m,
        checkpoint["jacobian_kn_per_m"],
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    internal_replay_match = _allclose_payload(
        replay.internal_forces_kn,
        checkpoint["internal_forces_kn"],
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    external_replay_match = _allclose_payload(
        replay.external_forces_kn,
        checkpoint["external_forces_kn"],
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    state_replay_match = _material_update_matches(
        replay.material_state_update,
        dict(checkpoint["material_state_update"]),
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    passed = (
        checkpoint.get("residual_formula") == RESIDUAL_FORMULA
        and residual_replay_match
        and tangent_replay_match
        and internal_replay_match
        and external_replay_match
        and state_replay_match
    )
    return {
        "schema_version": "g1-material-state-checkpoint-replay-check.v1",
        "pass": passed,
        "case_id": problem.case_id,
        "material_family": problem.material_family,
        "section_integration": problem.section_integration,
        "strain_mode": problem.strain_mode,
        "residual_formula": checkpoint.get("residual_formula"),
        "residual_replay_match": residual_replay_match,
        "tangent_replay_match": tangent_replay_match,
        "internal_force_replay_match": internal_replay_match,
        "external_force_replay_match": external_replay_match,
        "material_state_replay_match": state_replay_match,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "state_persistence_label": problem.state_persistence_label,
        "promotes_g1_closure": False,
    }


def check_state_updated_material_path_history_replay(
    checkpoint: dict[str, Any],
    *,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 1.0e-10,
) -> dict[str, Any]:
    """Replay a serialized material path history and its committed-state chain."""

    prior_committed_next: dict[str, Any] | None = None
    step_checks: list[dict[str, Any]] = []
    for step_payload in list(checkpoint.get("steps") or []):
        problem = StateUpdatedBilinearMaterialProblem(
            **dict(step_payload["problem"])
        )
        free_displacements = np.asarray(
            step_payload["free_displacements_m"],
            dtype=float,
        )
        replay = assemble_state_updated_material_newton_state(
            problem,
            free_displacements,
        )
        residual_replay_match = _allclose_payload(
            replay.residual_kn,
            step_payload["residual_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        tangent_replay_match = _allclose_payload(
            replay.jacobian_kn_per_m,
            step_payload["jacobian_kn_per_m"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        internal_replay_match = _allclose_payload(
            replay.internal_forces_kn,
            step_payload["internal_forces_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        external_replay_match = _allclose_payload(
            replay.external_forces_kn,
            step_payload["external_forces_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        state_replay_match = _material_update_matches(
            replay.material_state_update,
            dict(step_payload["material_state_update"]),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        carried_previous = dict(
            step_payload.get("carried_committed_state_previous") or {}
        )
        committed_previous = dict(
            replay.material_state_update.get("committed_state_previous") or {}
        )
        committed_next = dict(
            replay.material_state_update.get("committed_state_next") or {}
        )
        first_step_initial_state_match = True
        if prior_committed_next is None:
            first_step_initial_state_match = _material_update_matches(
                carried_previous,
                {
                    "plastic_displacement_m": (
                        problem.committed_plastic_displacement_m
                    ),
                    "equivalent_plastic_displacement_m": (
                        problem.committed_equivalent_plastic_displacement_m
                    ),
                },
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
        chain_link_from_previous_step_pass = True
        if prior_committed_next is not None:
            chain_link_from_previous_step_pass = _material_update_matches(
                carried_previous,
                prior_committed_next,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
        committed_previous_matches_carried_state = _material_update_matches(
            committed_previous,
            carried_previous,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        committed_state_chain_replay_pass = (
            step_payload.get("previous_committed_state_matches_carried_state")
            is True
            and first_step_initial_state_match
            and chain_link_from_previous_step_pass
            and committed_previous_matches_carried_state
        )
        step_passed = (
            step_payload.get("residual_formula") == RESIDUAL_FORMULA
            and residual_replay_match
            and tangent_replay_match
            and internal_replay_match
            and external_replay_match
            and state_replay_match
            and committed_state_chain_replay_pass
        )
        step_checks.append(
            {
                "pass": step_passed,
                "history_step_index": int(step_payload["history_step_index"]),
                "step_kind": str(step_payload["step_kind"]),
                "case_id": problem.case_id,
                "residual_formula": step_payload.get("residual_formula"),
                "residual_replay_match": residual_replay_match,
                "tangent_replay_match": tangent_replay_match,
                "internal_force_replay_match": internal_replay_match,
                "external_force_replay_match": external_replay_match,
                "material_state_replay_match": state_replay_match,
                "first_step_initial_state_match": first_step_initial_state_match,
                "chain_link_from_previous_step_pass": (
                    chain_link_from_previous_step_pass
                ),
                "committed_previous_matches_carried_state": (
                    committed_previous_matches_carried_state
                ),
                "committed_state_chain_replay_pass": (
                    committed_state_chain_replay_pass
                ),
                "path_dependent_state_updated": (
                    replay.material_state_update.get(
                        "path_dependent_state_updated"
                    )
                    is True
                ),
            }
        )
        prior_committed_next = committed_next

    step_replay_pass = all(step["pass"] for step in step_checks)
    committed_state_chain_replay_pass = all(
        step["committed_state_chain_replay_pass"] for step in step_checks
    )
    residual_replay_match = all(
        step["residual_replay_match"] for step in step_checks
    )
    tangent_replay_match = all(
        step["tangent_replay_match"] for step in step_checks
    )
    internal_replay_match = all(
        step["internal_force_replay_match"] for step in step_checks
    )
    external_replay_match = all(
        step["external_force_replay_match"] for step in step_checks
    )
    material_state_replay_match = all(
        step["material_state_replay_match"] for step in step_checks
    )
    passed = (
        checkpoint.get("schema_version")
        == "g1-material-path-history-checkpoint.seed.v1"
        and checkpoint.get("residual_formula") == RESIDUAL_FORMULA
        and int(checkpoint.get("step_count") or 0) == len(step_checks)
        and checkpoint.get("committed_state_chain_pass") is True
        and step_replay_pass
        and committed_state_chain_replay_pass
    )
    return {
        "schema_version": "g1-material-path-history-checkpoint-replay-check.v1",
        "pass": passed,
        "history_id": str(checkpoint.get("history_id") or ""),
        "step_count": len(step_checks),
        "path_dependent_update_step_count": sum(
            1 for step in step_checks if step["path_dependent_state_updated"]
        ),
        "residual_formula": checkpoint.get("residual_formula"),
        "step_replay_pass": step_replay_pass,
        "committed_state_chain_replay_pass": committed_state_chain_replay_pass,
        "residual_replay_match": residual_replay_match,
        "tangent_replay_match": tangent_replay_match,
        "internal_force_replay_match": internal_replay_match,
        "external_force_replay_match": external_replay_match,
        "material_state_replay_match": material_state_replay_match,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "steps": step_checks,
        "promotes_g1_closure": False,
    }


def check_frame_shell_coupled_material_load_step_replay(
    checkpoint: dict[str, Any],
    *,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 1.0e-10,
) -> dict[str, Any]:
    """Replay coupled frame/shell load steps and both committed-state chains."""

    prior_committed_next: dict[str, dict[str, Any]] | None = None
    step_checks: list[dict[str, Any]] = []
    for step_payload in list(checkpoint.get("steps") or []):
        problem_payload = dict(step_payload["problem"])
        problem = StateUpdatedFrameShellCoupledMaterialProblem(
            case_id=str(problem_payload["case_id"]),
            frame_problem=StateUpdatedBilinearMaterialProblem(
                **dict(problem_payload["frame_problem"])
            ),
            shell_problem=StateUpdatedBilinearMaterialProblem(
                **dict(problem_payload["shell_problem"])
            ),
            frame_shell_coupling_stiffness_kn_per_m=float(
                problem_payload["frame_shell_coupling_stiffness_kn_per_m"]
            ),
            external_force_kn=tuple(
                float(value) for value in problem_payload["external_force_kn"]
            ),
            initial_free_displacements_m=tuple(
                float(value)
                for value in problem_payload["initial_free_displacements_m"]
            ),
        )
        replay = assemble_state_updated_frame_shell_coupled_material_state(
            problem,
            np.asarray(step_payload["free_displacements_m"], dtype=float),
        )
        residual_replay_match = _allclose_payload(
            replay.residual_kn,
            step_payload["residual_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        tangent_replay_match = _allclose_payload(
            replay.jacobian_kn_per_m,
            step_payload["jacobian_kn_per_m"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        internal_replay_match = _allclose_payload(
            replay.internal_forces_kn,
            step_payload["internal_forces_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        external_replay_match = _allclose_payload(
            replay.external_forces_kn,
            step_payload["external_forces_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        component_state_replay_match = _component_material_states_match(
            replay.component_material_states,
            dict(step_payload["component_material_states"]),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        carried_previous = dict(
            step_payload.get("carried_component_committed_state_previous") or {}
        )
        component_states = dict(replay.component_material_states)
        committed_previous = {
            "frame": dict(
                component_states["frame"].get("committed_state_previous") or {}
            ),
            "shell": dict(
                component_states["shell"].get("committed_state_previous") or {}
            ),
        }
        committed_next = {
            "frame": _committed_state_from_update(component_states["frame"]),
            "shell": _committed_state_from_update(component_states["shell"]),
        }
        first_step_initial_state_match = True
        if prior_committed_next is None:
            first_step_initial_state_match = (
                _material_update_matches(
                    dict(carried_previous["frame"]),
                    _committed_state_from_problem(problem.frame_problem),
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
                and _material_update_matches(
                    dict(carried_previous["shell"]),
                    _committed_state_from_problem(problem.shell_problem),
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
            )
        chain_link_from_previous_step_pass = True
        if prior_committed_next is not None:
            chain_link_from_previous_step_pass = (
                _material_update_matches(
                    dict(carried_previous["frame"]),
                    prior_committed_next["frame"],
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
                and _material_update_matches(
                    dict(carried_previous["shell"]),
                    prior_committed_next["shell"],
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
            )
        committed_previous_matches_carried_state = (
            _material_update_matches(
                committed_previous["frame"],
                dict(carried_previous["frame"]),
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            and _material_update_matches(
                committed_previous["shell"],
                dict(carried_previous["shell"]),
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
        )
        committed_component_state_chain_replay_pass = (
            step_payload.get(
                "previous_component_committed_state_matches_carried_state"
            )
            is True
            and first_step_initial_state_match
            and chain_link_from_previous_step_pass
            and committed_previous_matches_carried_state
        )
        step_passed = (
            step_payload.get("residual_formula") == RESIDUAL_FORMULA
            and residual_replay_match
            and tangent_replay_match
            and internal_replay_match
            and external_replay_match
            and component_state_replay_match
            and committed_component_state_chain_replay_pass
        )
        step_checks.append(
            {
                "pass": step_passed,
                "history_step_index": int(step_payload["history_step_index"]),
                "step_kind": str(step_payload["step_kind"]),
                "case_id": problem.case_id,
                "residual_formula": step_payload.get("residual_formula"),
                "residual_replay_match": residual_replay_match,
                "tangent_replay_match": tangent_replay_match,
                "internal_force_replay_match": internal_replay_match,
                "external_force_replay_match": external_replay_match,
                "component_material_state_replay_match": (
                    component_state_replay_match
                ),
                "first_step_initial_state_match": first_step_initial_state_match,
                "chain_link_from_previous_step_pass": (
                    chain_link_from_previous_step_pass
                ),
                "committed_previous_matches_carried_state": (
                    committed_previous_matches_carried_state
                ),
                "committed_component_state_chain_replay_pass": (
                    committed_component_state_chain_replay_pass
                ),
                "frame_path_dependent_state_updated": (
                    component_states["frame"].get("path_dependent_state_updated")
                    is True
                ),
                "shell_path_dependent_state_updated": (
                    component_states["shell"].get("path_dependent_state_updated")
                    is True
                ),
            }
        )
        prior_committed_next = committed_next

    step_replay_pass = all(step["pass"] for step in step_checks)
    committed_component_state_chain_replay_pass = all(
        step["committed_component_state_chain_replay_pass"]
        for step in step_checks
    )
    residual_replay_match = all(
        step["residual_replay_match"] for step in step_checks
    )
    tangent_replay_match = all(
        step["tangent_replay_match"] for step in step_checks
    )
    internal_replay_match = all(
        step["internal_force_replay_match"] for step in step_checks
    )
    external_replay_match = all(
        step["external_force_replay_match"] for step in step_checks
    )
    component_state_replay_match = all(
        step["component_material_state_replay_match"] for step in step_checks
    )
    passed = (
        checkpoint.get("schema_version")
        == "g1-frame-shell-coupled-material-load-step-checkpoint.seed.v1"
        and checkpoint.get("residual_formula") == RESIDUAL_FORMULA
        and int(checkpoint.get("step_count") or 0) == len(step_checks)
        and checkpoint.get("committed_component_state_chain_pass") is True
        and step_replay_pass
        and committed_component_state_chain_replay_pass
    )
    return {
        "schema_version": (
            "g1-frame-shell-coupled-material-load-step-replay-check.v1"
        ),
        "pass": passed,
        "history_id": str(checkpoint.get("history_id") or ""),
        "step_count": len(step_checks),
        "path_dependent_update_step_count": sum(
            int(step["frame_path_dependent_state_updated"])
            + int(step["shell_path_dependent_state_updated"])
            for step in step_checks
        ),
        "residual_formula": checkpoint.get("residual_formula"),
        "step_replay_pass": step_replay_pass,
        "committed_component_state_chain_replay_pass": (
            committed_component_state_chain_replay_pass
        ),
        "residual_replay_match": residual_replay_match,
        "tangent_replay_match": tangent_replay_match,
        "internal_force_replay_match": internal_replay_match,
        "external_force_replay_match": external_replay_match,
        "component_material_state_replay_match": component_state_replay_match,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "steps": step_checks,
        "promotes_g1_closure": False,
    }


def check_material_mesh_load_step_replay(
    checkpoint: dict[str, Any],
    *,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 1.0e-10,
) -> dict[str, Any]:
    """Replay a serialized material mesh load-step history."""

    prior_committed_next: dict[str, dict[str, Any]] | None = None
    step_checks: list[dict[str, Any]] = []
    for step_payload in list(checkpoint.get("steps") or []):
        problem_payload = dict(step_payload["problem"])
        elements = []
        for element_payload in list(problem_payload.get("elements") or []):
            elements.append(
                StateUpdatedMaterialMeshElement(
                    element_id=str(element_payload["element_id"]),
                    node_i=int(element_payload["node_i"]),
                    node_j=int(element_payload["node_j"]),
                    material_problem=StateUpdatedBilinearMaterialProblem(
                        **dict(element_payload["material_problem"])
                    ),
                )
            )
        problem = StateUpdatedMaterialAxialChainMeshProblem(
            case_id=str(problem_payload["case_id"]),
            node_count=int(problem_payload["node_count"]),
            elements=tuple(elements),
            fixed_nodes=tuple(int(node) for node in problem_payload["fixed_nodes"]),
            external_forces_kn=tuple(
                (int(row["node_index"]), float(row["force_kn"]))
                for row in problem_payload["external_forces_kn"]
            ),
            initial_displacements_m=tuple(
                float(value) for value in problem_payload["initial_displacements_m"]
            ),
        )
        replay = assemble_state_updated_material_axial_chain_mesh_state(
            problem,
            np.asarray(step_payload["free_displacements_m"], dtype=float),
        )
        residual_replay_match = _allclose_payload(
            replay.residual_kn,
            step_payload["residual_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        tangent_replay_match = _allclose_payload(
            replay.jacobian_kn_per_m,
            step_payload["jacobian_kn_per_m"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        internal_replay_match = _allclose_payload(
            replay.internal_forces_kn,
            step_payload["internal_forces_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        external_replay_match = _allclose_payload(
            replay.external_forces_kn,
            step_payload["external_forces_kn"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        element_state_replay_match = _element_material_states_match(
            replay.element_material_states,
            tuple(step_payload["element_material_states"]),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        carried_previous = dict(
            step_payload.get("carried_element_committed_state_previous") or {}
        )
        replay_element_updates = {
            row["element_id"]: dict(row["material_state_update"])
            for row in replay.element_material_states
        }
        committed_previous = {
            element_id: dict(update.get("committed_state_previous") or {})
            for element_id, update in replay_element_updates.items()
        }
        committed_next = {
            element_id: _committed_state_from_update(update)
            for element_id, update in replay_element_updates.items()
        }
        first_step_initial_state_match = True
        if prior_committed_next is None:
            initial_committed = {
                element.element_id: _committed_state_from_problem(
                    element.material_problem
                )
                for element in problem.elements
            }
            first_step_initial_state_match = all(
                _material_update_matches(
                    dict(carried_previous[element_id]),
                    initial_committed[element_id],
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
                for element_id in initial_committed
            )
        chain_link_from_previous_step_pass = True
        if prior_committed_next is not None:
            chain_link_from_previous_step_pass = all(
                _material_update_matches(
                    dict(carried_previous[element_id]),
                    prior_committed_next[element_id],
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
                for element_id in prior_committed_next
            )
        committed_previous_matches_carried_state = all(
            _material_update_matches(
                committed_previous[element_id],
                dict(carried_previous[element_id]),
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            for element_id in committed_previous
        )
        committed_element_state_chain_replay_pass = (
            step_payload.get(
                "previous_element_committed_state_matches_carried_state"
            )
            is True
            and first_step_initial_state_match
            and chain_link_from_previous_step_pass
            and committed_previous_matches_carried_state
        )
        step_passed = (
            step_payload.get("residual_formula") == RESIDUAL_FORMULA
            and residual_replay_match
            and tangent_replay_match
            and internal_replay_match
            and external_replay_match
            and element_state_replay_match
            and committed_element_state_chain_replay_pass
        )
        step_checks.append(
            {
                "pass": step_passed,
                "history_step_index": int(step_payload["history_step_index"]),
                "step_kind": str(step_payload["step_kind"]),
                "case_id": problem.case_id,
                "residual_formula": step_payload.get("residual_formula"),
                "residual_replay_match": residual_replay_match,
                "tangent_replay_match": tangent_replay_match,
                "internal_force_replay_match": internal_replay_match,
                "external_force_replay_match": external_replay_match,
                "element_material_state_replay_match": element_state_replay_match,
                "first_step_initial_state_match": first_step_initial_state_match,
                "chain_link_from_previous_step_pass": (
                    chain_link_from_previous_step_pass
                ),
                "committed_previous_matches_carried_state": (
                    committed_previous_matches_carried_state
                ),
                "committed_element_state_chain_replay_pass": (
                    committed_element_state_chain_replay_pass
                ),
                "path_dependent_update_element_count": sum(
                    1
                    for update in replay_element_updates.values()
                    if update.get("path_dependent_state_updated") is True
                ),
            }
        )
        prior_committed_next = committed_next

    step_replay_pass = all(step["pass"] for step in step_checks)
    committed_element_state_chain_replay_pass = all(
        step["committed_element_state_chain_replay_pass"] for step in step_checks
    )
    residual_replay_match = all(
        step["residual_replay_match"] for step in step_checks
    )
    tangent_replay_match = all(
        step["tangent_replay_match"] for step in step_checks
    )
    internal_replay_match = all(
        step["internal_force_replay_match"] for step in step_checks
    )
    external_replay_match = all(
        step["external_force_replay_match"] for step in step_checks
    )
    element_state_replay_match = all(
        step["element_material_state_replay_match"] for step in step_checks
    )
    passed = (
        checkpoint.get("schema_version")
        == "g1-material-mesh-load-step-checkpoint.seed.v1"
        and checkpoint.get("residual_formula") == RESIDUAL_FORMULA
        and int(checkpoint.get("step_count") or 0) == len(step_checks)
        and checkpoint.get("committed_element_state_chain_pass") is True
        and step_replay_pass
        and committed_element_state_chain_replay_pass
    )
    return {
        "schema_version": "g1-material-mesh-load-step-replay-check.v1",
        "pass": passed,
        "history_id": str(checkpoint.get("history_id") or ""),
        "step_count": len(step_checks),
        "path_dependent_update_step_count": sum(
            int(step["path_dependent_update_element_count"])
            for step in step_checks
        ),
        "residual_formula": checkpoint.get("residual_formula"),
        "step_replay_pass": step_replay_pass,
        "committed_element_state_chain_replay_pass": (
            committed_element_state_chain_replay_pass
        ),
        "residual_replay_match": residual_replay_match,
        "tangent_replay_match": tangent_replay_match,
        "internal_force_replay_match": internal_replay_match,
        "external_force_replay_match": external_replay_match,
        "element_material_state_replay_match": element_state_replay_match,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "steps": step_checks,
        "promotes_g1_closure": False,
    }


def _return_mapping_update(
    problem: StateUpdatedBilinearMaterialProblem,
    displacement_m: float,
) -> dict[str, Any]:
    elastic = float(problem.elastic_stiffness_kn_per_m)
    hardening = float(problem.hardening_stiffness_kn_per_m)
    yield_force = float(problem.yield_force_kn)
    previous_plastic = float(problem.committed_plastic_displacement_m)
    previous_alpha = float(problem.committed_equivalent_plastic_displacement_m)

    trial_force = elastic * (float(displacement_m) - previous_plastic)
    yield_radius = yield_force + hardening * previous_alpha
    yield_function = abs(trial_force) - yield_radius
    previous_state = {
        "plastic_displacement_m": previous_plastic,
        "equivalent_plastic_displacement_m": previous_alpha,
    }
    common = {
        "material_model": "bilinear_isotropic_hardening_1d_return_mapping",
        "assembly_scope": problem.assembly_scope,
        "structural_component": problem.structural_component,
        "material_case_kind": problem.material_case_kind,
        "material_family": problem.material_family,
        "section_integration": problem.section_integration,
        "strain_mode": problem.strain_mode,
        "state_persistence_label": problem.state_persistence_label,
        "material_admissibility": problem.admissibility.to_dict(),
    }
    if yield_function <= 0.0:
        return {
            **common,
            "return_mapping": "elastic_trial_state",
            "trial_displacement_m": float(displacement_m),
            "trial_force_kn": trial_force,
            "yield_function_kn": yield_function,
            "yielded": False,
            "committed_state_previous": previous_state,
            "committed_state_next": previous_state,
            "plastic_increment_m": 0.0,
            "internal_force_kn": trial_force,
            "algorithmic_tangent_kn_per_m": elastic,
            "path_dependent_state_updated": False,
        }

    sign = 1.0 if trial_force >= 0.0 else -1.0
    plastic_increment = yield_function / (elastic + hardening)
    next_plastic = previous_plastic + sign * plastic_increment
    next_alpha = previous_alpha + plastic_increment
    internal_force = trial_force - sign * elastic * plastic_increment
    algorithmic_tangent = elastic * hardening / (elastic + hardening)
    return {
        **common,
        "return_mapping": "plastic_corrector",
        "trial_displacement_m": float(displacement_m),
        "trial_force_kn": trial_force,
        "yield_function_kn": yield_function,
        "yielded": True,
        "committed_state_previous": previous_state,
        "committed_state_next": {
            "plastic_displacement_m": next_plastic,
            "equivalent_plastic_displacement_m": next_alpha,
        },
        "plastic_increment_m": plastic_increment,
        "internal_force_kn": internal_force,
        "algorithmic_tangent_kn_per_m": algorithmic_tangent,
        "path_dependent_state_updated": True,
    }


def _allclose_payload(
    actual: Any,
    expected: Any,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> bool:
    return bool(
        np.allclose(
            np.asarray(actual, dtype=float),
            np.asarray(expected, dtype=float),
            atol=absolute_tolerance,
            rtol=relative_tolerance,
        )
    )


def _committed_state_from_problem(
    problem: StateUpdatedBilinearMaterialProblem,
) -> dict[str, float]:
    return {
        "plastic_displacement_m": float(problem.committed_plastic_displacement_m),
        "equivalent_plastic_displacement_m": float(
            problem.committed_equivalent_plastic_displacement_m
        ),
    }


def _committed_state_from_update(update: dict[str, Any]) -> dict[str, float]:
    committed_next = dict(update.get("committed_state_next") or {})
    return {
        "plastic_displacement_m": float(committed_next["plastic_displacement_m"]),
        "equivalent_plastic_displacement_m": float(
            committed_next["equivalent_plastic_displacement_m"]
        ),
    }


def _component_material_states_match(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> bool:
    if set(actual) != set(expected):
        return False
    return all(
        _material_update_matches(
            dict(actual[key]),
            dict(expected[key]),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        for key in actual
    )


def _element_material_states_match(
    actual: tuple[dict[str, Any], ...],
    expected: tuple[dict[str, Any], ...],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> bool:
    if len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(actual, expected):
        if set(actual_row) != set(expected_row):
            return False
        for key, actual_value in actual_row.items():
            expected_value = expected_row[key]
            if key == "material_state_update":
                if not _material_update_matches(
                    dict(actual_value),
                    dict(expected_value),
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                ):
                    return False
                continue
            if isinstance(actual_value, (int, float)) and isinstance(
                expected_value,
                (int, float),
            ):
                if not np.isclose(
                    float(actual_value),
                    float(expected_value),
                    atol=absolute_tolerance,
                    rtol=relative_tolerance,
                ):
                    return False
                continue
            if actual_value != expected_value:
                return False
    return True


def _material_update_matches(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> bool:
    if set(actual) != set(expected):
        return False
    for key, actual_value in actual.items():
        expected_value = expected[key]
        if isinstance(actual_value, dict) and isinstance(expected_value, dict):
            if not _material_update_matches(
                actual_value,
                expected_value,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            ):
                return False
            continue
        if isinstance(actual_value, bool) or isinstance(expected_value, bool):
            if actual_value is not expected_value:
                return False
            continue
        if isinstance(actual_value, (int, float)) and isinstance(
            expected_value,
            (int, float),
        ):
            if not np.isclose(
                float(actual_value),
                float(expected_value),
                atol=absolute_tolerance,
                rtol=relative_tolerance,
            ):
                return False
            continue
        if actual_value != expected_value:
            return False
    return True
