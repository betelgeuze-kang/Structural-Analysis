from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_g1_assembly_contract_seed_report.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_g1_assembly_contract_seed_report",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_axial_chain_seed_adapts_to_g1_assembly_contract() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.nonlinear_static import (
        assemble_axial_chain_state,
        default_phase2_axial_chain_mesh_problem,
        solve_axial_chain_mesh,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = default_phase2_axial_chain_mesh_problem()
    solution, state = solve_axial_chain_mesh(
        problem,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        ),
    )
    result = assemble_g1_state(problem, state)
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_axial_chain_state(problem, free_u),
        ),
        solution.free_displacements_m,
    )
    newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_axial_chain_state(problem, free_u),
        ),
        solution,
    )

    assert result.schema_version == "g1-assembly-result.v1"
    assert result.residual_formula == "F_internal_minus_F_external"
    assert np.allclose(
        result.residual_free,
        result.internal_forces[list(state.free_node_indices)]
        - result.external_forces[list(state.free_node_indices)],
    )
    assert result.tangent_free.shape == (2, 2)
    assert result.material_state_next["state_updated_material_newton"] is False
    assert result.metrics["regularized_fixed_point_substitute"] is False
    assert result.metrics["g1_closure_claim"] is False
    assert result.contract_check()["contract_pass"] is True
    assert jvp_check["pass"] is True
    assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True
    assert newton_parity["consistent_residual_jacobian_newton_gate_passed"] is False
    assert newton_parity["direct_solver_residual_match"] is True
    assert newton_parity["residual_descent_passed"] is True
    assert newton_parity["relative_increment_gate_passed"] is True
    assert newton_parity["promotes_g1_closure"] is False


def test_frame_shell_material_seed_adapts_to_g1_assembly_contract() -> None:
    from structural_analysis.assembly.coupled_static import (
        assemble_frame_shell_material_coupled_state,
        default_frame_shell_material_coupled_problem,
        solve_frame_shell_material_coupled,
    )
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = default_frame_shell_material_coupled_problem()
    solution, state = solve_frame_shell_material_coupled(
        problem,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        ),
    )
    result = assemble_g1_state(problem, state)
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_frame_shell_material_coupled_state(problem, free_u),
        ),
        solution.free_displacements_m,
    )
    newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_frame_shell_material_coupled_state(problem, free_u),
        ),
        solution,
    )

    assert result.residual_formula == "F_internal_minus_F_external"
    assert np.allclose(
        result.residual_free,
        result.internal_forces - result.external_forces,
    )
    assert result.tangent_free.shape == (2, 2)
    assert result.tangent_free[0, 1] == result.tangent_free[1, 0]
    assert result.material_state_next["state_updated_material_newton"] is False
    assert result.metrics["fixed_point_residual_used_as_physical"] is False
    assert result.metrics["g1_closure_claim"] is False
    assert result.contract_check()["contract_pass"] is True
    assert jvp_check["pass"] is True
    assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True
    assert newton_parity["consistent_residual_jacobian_newton_gate_passed"] is False
    assert newton_parity["direct_solver_residual_match"] is True
    assert newton_parity["residual_descent_passed"] is True
    assert newton_parity["relative_increment_gate_passed"] is True
    assert newton_parity["promotes_g1_closure"] is False


def test_state_updated_material_seed_adapts_to_g1_assembly_contract() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.material_state import (
        assemble_state_updated_material_newton_state,
        default_state_updated_bilinear_material_problem,
        solve_state_updated_material_newton,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = default_state_updated_bilinear_material_problem()
    solution, state = solve_state_updated_material_newton(
        problem,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        ),
    )
    result = assemble_g1_state(problem, state)
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_state_updated_material_newton_state(problem, free_u),
        ),
        solution.free_displacements_m,
    )
    newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_state_updated_material_newton_state(problem, free_u),
        ),
        solution,
    )

    material_state = result.material_state_next
    trial_state = material_state["trial_state"]
    committed_next = material_state["committed_state_next"]

    assert result.residual_formula == "F_internal_minus_F_external"
    assert np.allclose(result.residual_free, result.internal_forces - result.external_forces)
    assert result.tangent_free.shape == (1, 1)
    assert result.tangent_free[0, 0] == pytest.approx(40.0)
    assert material_state["state_updated_material_newton"] is True
    assert material_state["path_dependent_state"] is True
    assert material_state["path_dependent_state_updated"] is True
    assert material_state["material_family"] == "reinforced_concrete"
    assert material_state["section_integration"] == "frame_fiber"
    assert material_state["strain_mode"] == "axial"
    assert material_state["return_mapping"] == "plastic_corrector"
    assert trial_state["yielded"] is True
    assert committed_next["plastic_displacement_m"] > 0.0
    assert committed_next["equivalent_plastic_displacement_m"] > 0.0
    assert result.metrics["state_updated_material_newton"] is True
    assert result.metrics["regularized_fixed_point_substitute"] is False
    assert result.metrics["g1_closure_claim"] is False
    assert result.contract_check()["contract_pass"] is True
    assert jvp_check["pass"] is True
    assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True
    assert newton_parity["consistent_residual_jacobian_newton_gate_passed"] is False
    assert newton_parity["direct_solver_residual_match"] is True
    assert newton_parity["residual_descent_passed"] is True
    assert newton_parity["relative_increment_gate_passed"] is True
    assert newton_parity["promotes_g1_closure"] is False


def test_state_updated_frame_shell_coupled_material_seed_adapts_to_g1_contract() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.material_state import (
        assemble_state_updated_frame_shell_coupled_material_state,
        default_state_updated_frame_shell_coupled_material_problem,
        solve_state_updated_frame_shell_coupled_material_newton,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = default_state_updated_frame_shell_coupled_material_problem()
    solution, state = solve_state_updated_frame_shell_coupled_material_newton(
        problem,
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        ),
    )
    result = assemble_g1_state(problem, state)
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_state_updated_frame_shell_coupled_material_state(
                problem,
                free_u,
            ),
        ),
        solution.free_displacements_m,
    )
    newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_state_updated_frame_shell_coupled_material_state(
                problem,
                free_u,
            ),
        ),
        solution,
    )

    material_state = result.material_state_next

    assert result.residual_formula == "F_internal_minus_F_external"
    assert np.allclose(result.residual_free, result.internal_forces - result.external_forces)
    assert result.tangent_free.shape == (2, 2)
    assert result.tangent_free[0, 1] == pytest.approx(result.tangent_free[1, 0])
    assert material_state["state_updated_material_newton"] is True
    assert material_state["frame_shell_state_updated_material_coupling"] is True
    assert material_state["frame_material_state_updated"] is True
    assert material_state["shell_material_state_updated"] is True
    assert material_state["component_return_mappings"] == {
        "frame": "plastic_corrector",
        "shell": "plastic_corrector",
    }
    assert result.metrics["frame_shell_state_updated_material_coupling"] is True
    assert result.metrics["regularized_fixed_point_substitute"] is False
    assert result.metrics["g1_closure_claim"] is False
    assert result.contract_check()["contract_pass"] is True
    assert jvp_check["pass"] is True
    assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True
    assert newton_parity["consistent_residual_jacobian_newton_gate_passed"] is False
    assert newton_parity["direct_solver_residual_match"] is True
    assert newton_parity["residual_descent_passed"] is True
    assert newton_parity["relative_increment_gate_passed"] is True
    assert newton_parity["promotes_g1_closure"] is False


def test_state_updated_material_breadth_seeds_preserve_path_dependent_contract() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.material_state import (
        assemble_state_updated_material_newton_state,
        check_state_updated_material_checkpoint_replay,
        default_state_updated_bilinear_material_breadth_problems,
        material_state_checkpoint_payload,
        solve_state_updated_material_newton,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    rows = []
    for problem in default_state_updated_bilinear_material_breadth_problems():
        solution, state = solve_state_updated_material_newton(problem, config=config)
        result = assemble_g1_state(problem, state)
        checkpoint = material_state_checkpoint_payload(problem, state)
        checkpoint_replay = check_state_updated_material_checkpoint_replay(
            json.loads(json.dumps(checkpoint, ensure_ascii=False))
        )
        jvp_check = finite_difference_g1_jvp_check(
            lambda free_u, seed=problem: assemble_g1_state(
                seed,
                assemble_state_updated_material_newton_state(seed, free_u),
            ),
            solution.free_displacements_m,
        )
        newton_parity = direct_residual_newton_parity_check(
            lambda free_u, seed=problem: assemble_g1_state(
                seed,
                assemble_state_updated_material_newton_state(seed, free_u),
            ),
            solution,
        )
        material_state = result.material_state_next
        rows.append(
            {
                "kind": material_state["material_case_kind"],
                "component": material_state["structural_component"],
                "updated": material_state["path_dependent_state_updated"],
                "family": material_state["material_family"],
                "section_integration": material_state["section_integration"],
                "strain_mode": material_state["strain_mode"],
                "return_mapping": material_state["return_mapping"],
                "jvp_pass": jvp_check["pass"],
                "parity_pass": newton_parity[
                    "cpu_seed_consistent_newton_gate_passed"
                ],
                "checkpoint_replay_pass": checkpoint_replay["pass"],
                "closure_claim": result.metrics["g1_closure_claim"],
            }
        )

    assert {row["kind"] for row in rows} == {
        "monotonic_tension_yield",
        "monotonic_steel_tension_yield",
        "elastic_only_replay",
        "monotonic_compression_yield",
        "monotonic_shell_bending_yield",
        "elastic_drilling_stiffness_replay",
        "plastic_reloading_from_committed_state",
        "elastic_unloading_from_committed_state",
        "reverse_compression_from_committed_state",
    }
    assert {row["component"] for row in rows} == {
        "frame_fiber_axial",
        "steel_frame_fiber_axial",
        "shell_layer_membrane",
        "shell_layer_bending",
        "shell_drilling_stiffness",
        "src_composite_axial",
        "rc_frame_fiber_axial",
    }
    assert {row["family"] for row in rows} == {
        "reinforced_concrete",
        "steel",
        "src_composite",
        "shell_equivalent_plate",
    }
    assert {row["section_integration"] for row in rows} == {
        "frame_fiber",
        "layered_shell",
        "composite_fiber",
    }
    assert {row["strain_mode"] for row in rows} == {
        "axial",
        "membrane",
        "bending",
        "drilling",
        "axial_reverse",
    }
    assert all(row["jvp_pass"] is True for row in rows)
    assert all(row["parity_pass"] is True for row in rows)
    assert all(row["checkpoint_replay_pass"] is True for row in rows)
    assert all(row["closure_claim"] is False for row in rows)
    assert sum(row["updated"] is True for row in rows) == 6
    assert any(row["return_mapping"] == "elastic_trial_state" for row in rows)


def test_state_updated_material_path_histories_carry_committed_state() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.material_state import (
        assemble_state_updated_material_newton_state,
        check_state_updated_material_path_history_replay,
        material_path_history_checkpoint_payload,
        solve_default_state_updated_material_path_histories,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    histories = solve_default_state_updated_material_path_histories(
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        )
    )

    assert len(histories) == 2
    assert sum(len(history.steps) for history in histories) == 7
    assert sum(
        history.path_dependent_update_step_count for history in histories
    ) == 4
    for history in histories:
        assert history.committed_state_chain_pass is True
        checkpoint = material_path_history_checkpoint_payload(history)
        replay = check_state_updated_material_path_history_replay(
            json.loads(json.dumps(checkpoint, ensure_ascii=False))
        )
        assert replay["pass"] is True
        assert replay["step_count"] == len(history.steps)
        assert replay["step_replay_pass"] is True
        assert replay["committed_state_chain_replay_pass"] is True
        assert replay["material_state_replay_match"] is True
        for step in history.steps:
            result = assemble_g1_state(step.problem, step.state)
            jvp_check = finite_difference_g1_jvp_check(
                lambda free_u, problem=step.problem: assemble_g1_state(
                    problem,
                    assemble_state_updated_material_newton_state(problem, free_u),
                ),
                step.solution.free_displacements_m,
            )
            newton_parity = direct_residual_newton_parity_check(
                lambda free_u, problem=step.problem: assemble_g1_state(
                    problem,
                    assemble_state_updated_material_newton_state(problem, free_u),
                ),
                step.solution,
            )

            assert step.previous_committed_state_matches_carried_state is True
            assert result.material_state_next["path_dependent_state"] is True
            assert jvp_check["pass"] is True
            assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True
            assert result.metrics["g1_closure_claim"] is False


def test_state_updated_frame_shell_coupled_load_step_history_carries_component_states() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.material_state import (
        assemble_state_updated_frame_shell_coupled_material_state,
        check_frame_shell_coupled_material_load_step_replay,
        frame_shell_coupled_material_load_step_checkpoint_payload,
        solve_state_updated_frame_shell_coupled_material_load_step_history,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    history = solve_state_updated_frame_shell_coupled_material_load_step_history(
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        )
    )

    assert history.history_id == "frame_shell_coupled_material_load_step_reversal_history"
    assert len(history.steps) == 4
    assert history.committed_component_state_chain_pass is True
    assert history.path_dependent_update_step_count == 4
    checkpoint = frame_shell_coupled_material_load_step_checkpoint_payload(history)
    replay = check_frame_shell_coupled_material_load_step_replay(
        json.loads(json.dumps(checkpoint, ensure_ascii=False))
    )
    assert replay["pass"] is True
    assert replay["step_count"] == 4
    assert replay["step_replay_pass"] is True
    assert replay["committed_component_state_chain_replay_pass"] is True
    assert replay["component_material_state_replay_match"] is True

    return_mappings = []
    for step in history.steps:
        result = assemble_g1_state(step.problem, step.state)
        jvp_check = finite_difference_g1_jvp_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_frame_shell_coupled_material_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution.free_displacements_m,
        )
        newton_parity = direct_residual_newton_parity_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_frame_shell_coupled_material_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution,
        )
        material_state = result.material_state_next
        return_mappings.append(
            (
                material_state["component_return_mappings"]["frame"],
                material_state["component_return_mappings"]["shell"],
            )
        )
        assert step.previous_component_committed_state_matches_carried_state is True
        assert material_state["frame_shell_state_updated_material_coupling"] is True
        assert result.metrics["g1_closure_claim"] is False
        assert jvp_check["pass"] is True
        assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True

    assert return_mappings == [
        ("plastic_corrector", "plastic_corrector"),
        ("elastic_trial_state", "elastic_trial_state"),
        ("plastic_corrector", "plastic_corrector"),
        ("elastic_trial_state", "elastic_trial_state"),
    ]


def test_state_updated_material_mesh_load_step_history_carries_element_states() -> None:
    from structural_analysis.assembly.g1_contract import (
        assemble_g1_state,
        direct_residual_newton_parity_check,
        finite_difference_g1_jvp_check,
    )
    from structural_analysis.assembly.material_state import (
        assemble_state_updated_material_axial_chain_mesh_state,
        check_material_mesh_load_step_replay,
        material_mesh_load_step_checkpoint_payload,
        solve_state_updated_material_mesh_load_step_history,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    history = solve_state_updated_material_mesh_load_step_history(
        config=NewtonRaphsonConfig(
            residual_tolerance=1.0e-10,
            increment_tolerance=1.0e-12,
            max_iterations=25,
        )
    )

    assert history.history_id == "state_updated_material_axial_chain_mesh_load_step_history"
    assert len(history.steps) == 4
    assert history.committed_element_state_chain_pass is True
    assert history.path_dependent_update_step_count == 4
    checkpoint = material_mesh_load_step_checkpoint_payload(history)
    replay = check_material_mesh_load_step_replay(
        json.loads(json.dumps(checkpoint, ensure_ascii=False))
    )
    assert replay["pass"] is True
    assert replay["step_count"] == 4
    assert replay["step_replay_pass"] is True
    assert replay["committed_element_state_chain_replay_pass"] is True
    assert replay["element_material_state_replay_match"] is True

    update_counts = []
    for step in history.steps:
        result = assemble_g1_state(step.problem, step.state)
        jvp_check = finite_difference_g1_jvp_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_material_axial_chain_mesh_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution.free_displacements_m,
        )
        newton_parity = direct_residual_newton_parity_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_material_axial_chain_mesh_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution,
        )
        material_state = result.material_state_next
        update_counts.append(material_state["path_dependent_update_element_count"])

        assert step.previous_element_committed_state_matches_carried_state is True
        assert material_state["state_updated_material_mesh"] is True
        assert result.metrics["state_updated_material_mesh"] is True
        assert result.metrics["g1_closure_claim"] is False
        assert jvp_check["pass"] is True
        assert newton_parity["cpu_seed_consistent_newton_gate_passed"] is True

    assert update_counts == [2, 0, 2, 0]


def test_g1_assembly_contract_rejects_fixed_point_physical_residual_substitute() -> None:
    from structural_analysis.assembly.g1_contract import AssemblyResult

    with pytest.raises(ValueError, match="substitute"):
        AssemblyResult(
            residual_formula="F_internal_minus_F_external",
            residual_source="fixed_point_residual",
            residual_free=np.array([0.0]),
            tangent_free=np.array([[1.0]]),
            internal_forces=np.array([1.0]),
            external_forces=np.array([1.0]),
            material_state_next={},
            metrics={"fixed_point_residual_used_as_physical": True},
        )


def test_g1_assembly_contract_seed_report_is_non_promoting_ready_receipt() -> None:
    payload = module.build_g1_assembly_contract_seed_report(repo_root=REPO_ROOT)

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["g1_closure_claim"] is False
    assert (
        payload["phase_covered"]
        == "phase1_phase2_cpu_seed_contract_newton_parity_and_state_updated_material_breadth_seeds"
    )
    assert payload["residual_formula"] == "F_internal_minus_F_external"
    assert payload["fixed_point_residual_promoted_to_physical"] is False
    assert payload["regularized_fixed_point_substitute"] is False
    assert payload["cpu_seed_consistent_newton_gate_passed"] is True
    assert payload["consistent_residual_jacobian_newton_gate_passed"] is False
    assert payload["state_updated_material_newton_seed_passed"] is True
    assert payload["state_updated_material_newton_breadth_closed"] is False
    assert payload["state_updated_material_newton_seed_case_count"] == 9
    assert payload["state_updated_material_newton_seed_case_kinds"] == [
        "monotonic_tension_yield",
        "monotonic_steel_tension_yield",
        "elastic_only_replay",
        "monotonic_compression_yield",
        "monotonic_shell_bending_yield",
        "elastic_drilling_stiffness_replay",
        "plastic_reloading_from_committed_state",
        "elastic_unloading_from_committed_state",
        "reverse_compression_from_committed_state",
    ]
    assert payload["state_updated_material_newton_seed_structural_components"] == [
        "frame_fiber_axial",
        "rc_frame_fiber_axial",
        "shell_drilling_stiffness",
        "shell_layer_bending",
        "shell_layer_membrane",
        "src_composite_axial",
        "steel_frame_fiber_axial",
    ]
    assert payload["state_updated_material_newton_seed_material_families"] == [
        "reinforced_concrete",
        "shell_equivalent_plate",
        "src_composite",
        "steel",
    ]
    assert payload["state_updated_material_newton_seed_section_integrations"] == [
        "composite_fiber",
        "frame_fiber",
        "layered_shell",
    ]
    assert payload["state_updated_material_newton_seed_strain_modes"] == [
        "axial",
        "axial_reverse",
        "bending",
        "drilling",
        "membrane",
    ]
    assert payload["path_dependent_material_update_seed_case_count"] == 6
    assert payload["path_dependent_material_replay_seed_case_count"] == 9
    assert payload["material_state_persistence_replay_seed_passed"] is True
    assert payload["material_state_persistence_replay_seed_case_count"] == 9
    assert payload["state_updated_material_newton_breadth_seed_coverage_ready"] is True
    assert payload["material_jvp_max_relative_error"] <= 1.0e-6
    assert payload["state_updated_material_path_history_passed"] is True
    assert payload["state_updated_material_path_history_count"] == 2
    assert payload["state_updated_material_path_history_step_count"] == 7
    assert payload["state_updated_material_path_history_update_step_count"] == 4
    assert payload["state_updated_material_path_history_checkpoint_replay_pass"] is True
    assert payload["state_updated_material_path_history_chain_replay_pass"] is True
    assert payload["state_updated_material_path_history_jvp_pass"] is True
    assert payload["state_updated_material_path_history_direct_parity_pass"] is True
    assert payload["state_updated_material_path_history_committed_chain_pass"] is True
    assert all(
        row["pass"] is True
        and row["committed_state_chain_replay_pass"] is True
        for row in payload["state_updated_material_path_history_replay_checks"]
    )
    assert payload["state_updated_frame_shell_coupled_material_seed_passed"] is True
    assert (
        payload[
            "state_updated_frame_shell_coupled_material_component_updates_pass"
        ]
        is True
    )
    assert payload["state_updated_frame_shell_coupled_material_jvp_pass"] is True
    assert (
        payload["state_updated_frame_shell_coupled_material_direct_parity_pass"]
        is True
    )
    assert payload["state_updated_frame_shell_coupled_load_step_history_passed"] is True
    assert payload["state_updated_frame_shell_coupled_load_step_history_step_count"] == 4
    assert (
        payload[
            "state_updated_frame_shell_coupled_load_step_history_update_step_count"
        ]
        == 4
    )
    assert (
        payload[
            "state_updated_frame_shell_coupled_load_step_history_checkpoint_replay_pass"
        ]
        is True
    )
    assert (
        payload[
            "state_updated_frame_shell_coupled_load_step_history_chain_replay_pass"
        ]
        is True
    )
    assert payload["state_updated_frame_shell_coupled_load_step_history_jvp_pass"] is True
    assert (
        payload[
            "state_updated_frame_shell_coupled_load_step_history_direct_parity_pass"
        ]
        is True
    )
    assert (
        payload["state_updated_frame_shell_coupled_load_step_history_replay_check"][
            "pass"
        ]
        is True
    )
    assert payload["state_updated_material_mesh_load_step_history_passed"] is True
    assert payload["state_updated_material_mesh_load_step_history_step_count"] == 4
    assert (
        payload["state_updated_material_mesh_load_step_history_update_step_count"]
        == 4
    )
    assert (
        payload[
            "state_updated_material_mesh_load_step_history_checkpoint_replay_pass"
        ]
        is True
    )
    assert (
        payload["state_updated_material_mesh_load_step_history_chain_replay_pass"]
        is True
    )
    assert payload["state_updated_material_mesh_load_step_history_jvp_pass"] is True
    assert (
        payload["state_updated_material_mesh_load_step_history_direct_parity_pass"]
        is True
    )
    assert (
        payload["state_updated_material_mesh_load_step_history_replay_check"][
            "pass"
        ]
        is True
    )
    assert payload["case_count"] == 27
    assert all(row["contract_pass"] is True for row in payload["cases"])
    material_cases = [
        row
        for row in payload["cases"]
        if row["assembly_result"]["material_state_next"].get(
            "state_updated_material_newton"
        )
        is True
    ]
    assert len(material_cases) == 25
    material_states = [
        row["assembly_result"]["material_state_next"] for row in material_cases
    ]
    assert all(row["state_updated_material_newton"] is True for row in material_states)
    assert sum(row["path_dependent_state_updated"] is True for row in material_states) == 15
    one_dof_material_states = [
        row for row in material_states if "return_mapping" in row
    ]
    assert {row["return_mapping"] for row in one_dof_material_states} == {
        "plastic_corrector",
        "elastic_trial_state",
    }
    coupled_material_states = [
        row
        for row in material_states
        if row.get("frame_shell_state_updated_material_coupling") is True
    ]
    assert len(coupled_material_states) == 5
    assert [
        row["component_return_mappings"] for row in coupled_material_states
    ] == [
        {"frame": "plastic_corrector", "shell": "plastic_corrector"},
        {"frame": "plastic_corrector", "shell": "plastic_corrector"},
        {"frame": "elastic_trial_state", "shell": "elastic_trial_state"},
        {"frame": "plastic_corrector", "shell": "plastic_corrector"},
        {"frame": "elastic_trial_state", "shell": "elastic_trial_state"},
    ]
    path_history_cases = [
        row for row in material_cases if "material_path_history" in row
    ]
    assert len(path_history_cases) == 7
    assert all(
        row["material_path_history"][
            "previous_committed_state_matches_carried_state"
        ]
        is True
        for row in path_history_cases
    )
    assert all(
        row["material_path_history"]["history_chain_replay_pass"] is True
        for row in path_history_cases
    )
    coupled_load_step_cases = [
        row
        for row in material_cases
        if "frame_shell_coupled_load_step_history" in row
    ]
    assert len(coupled_load_step_cases) == 4
    assert all(
        row["frame_shell_coupled_load_step_history"][
            "previous_component_committed_state_matches_carried_state"
        ]
        is True
        for row in coupled_load_step_cases
    )
    assert all(
        row["frame_shell_coupled_load_step_history"]["history_chain_replay_pass"]
        is True
        for row in coupled_load_step_cases
    )
    material_mesh_states = [
        row
        for row in material_states
        if row.get("state_updated_material_mesh") is True
    ]
    assert len(material_mesh_states) == 4
    assert [
        row["path_dependent_update_element_count"] for row in material_mesh_states
    ] == [2, 0, 2, 0]
    material_mesh_load_step_cases = [
        row for row in material_cases if "material_mesh_load_step_history" in row
    ]
    assert len(material_mesh_load_step_cases) == 4
    assert all(
        row["material_mesh_load_step_history"][
            "previous_element_committed_state_matches_carried_state"
        ]
        is True
        for row in material_mesh_load_step_cases
    )
    assert all(
        row["material_mesh_load_step_history"]["history_chain_replay_pass"] is True
        for row in material_mesh_load_step_cases
    )
    assert all(
        row["material_state_persistence_replay_check"]["pass"] is True
        for row in material_cases
        if "material_state_persistence_replay_check" in row
    )
    assert all(
        row["jvp_finite_difference_check"]["pass"] is True
        for row in payload["cases"]
    )
    assert all(
        row["direct_residual_newton_parity_check"][
            "cpu_seed_consistent_newton_gate_passed"
        ]
        is True
        for row in payload["cases"]
    )
    assert all(
        row["direct_residual_newton_parity_check"][
            "direct_solver_residual_match"
        ]
        is True
        for row in payload["cases"]
    )
    assert payload["blockers_remaining"] == [
        "full_load_gate_not_closed",
        "full_mesh_nonlinear_equilibrium_not_closed",
        "material_newton_breadth_not_closed",
        "production_rocm_hip_residency_not_closed",
        "g1_consistent_residual_jacobian_newton_gate_not_closed_by_cpu_seed",
        "full_load_checkpoint_1p0_not_created_by_this_seed_report",
        "hip_residual_jvp_worker_not_executed_by_this_seed_report",
    ]


def test_g1_assembly_contract_seed_report_check_detects_missing_output(
    tmp_path: Path,
) -> None:
    ok, message = module.check_g1_assembly_contract_seed_report(
        repo_root=REPO_ROOT,
        out=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("g1_assembly_contract_seed_report_missing:")


def test_g1_assembly_contract_seed_report_check_ignores_wrapper_source_commit(
    tmp_path: Path,
) -> None:
    out = tmp_path / "g1_assembly_contract_seed_report.json"
    payload = module.write_g1_assembly_contract_seed_report(
        repo_root=REPO_ROOT,
        out=out,
    )
    payload["source_commit_sha"] = "receipt-only-followup-commit"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ok, message = module.check_g1_assembly_contract_seed_report(
        repo_root=REPO_ROOT,
        out=out,
    )

    assert ok is True
    assert message == "g1_assembly_contract_seed_report_consistent"


def test_g1_assembly_contract_seed_report_check_detects_semantic_mismatch(
    tmp_path: Path,
) -> None:
    out = tmp_path / "g1_assembly_contract_seed_report.json"
    payload = module.write_g1_assembly_contract_seed_report(
        repo_root=REPO_ROOT,
        out=out,
    )
    payload["contract_pass"] = False
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ok, message = module.check_g1_assembly_contract_seed_report(
        repo_root=REPO_ROOT,
        out=out,
    )

    assert ok is False
    assert message == "g1_assembly_contract_seed_report_mismatch"
