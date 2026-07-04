"""State-updated material Newton seed assembly."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

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

    def reference_force_scale(self) -> float:
        return max(abs(self.external_force_kn), 1.0)


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
