from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    initial_stateful_axial_state,
    two_element_bilinear_link_chain_problem,
    two_element_composite_section_chain_problem,
    two_element_concrete_damage_chain_problem,
    two_element_stateful_steel_chain_problem,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_json_bytes
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (
    LoadControlledMatrixFreeNewtonConfig,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.solvers.nonlinear.stateful_axial_adaptive_matrix_free_newton import (
    STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION,
    StatefulAxialAdaptiveMatrixFreeNewtonConfig,
    StatefulAxialAdaptiveMatrixFreeNewtonError,
    adaptive_stateful_axial_matrix_free_newton_continuation,
    load_stateful_axial_adaptive_matrix_free_checkpoint_bytes,
    read_stateful_axial_adaptive_matrix_free_checkpoint_artifact,
    write_stateful_axial_adaptive_matrix_free_checkpoint_artifact,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthTangentSolve,
)


_FAULT_FACTORY_CONTRACT_HASH = "sha256:" + "1" * 64


def _step_config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(1.0,),
        residual_tolerance_inf_kn=1.0e-9,
        increment_absolute_tolerance_inf_m=1.0e-12,
        increment_relative_tolerance=1.0e-9,
        tangent_solve_residual_tolerance_inf_kn=1.0e-9,
        maximum_newton_iterations=8,
    )


def _adaptive_config() -> StatefulAxialAdaptiveMatrixFreeNewtonConfig:
    return StatefulAxialAdaptiveMatrixFreeNewtonConfig(
        target_load_factor=1.0,
        initial_step_size=1.0,
        minimum_step_size=0.25,
        maximum_step_size=1.0,
        failed_step_reduction=0.5,
        fast_step_growth=2.0,
        fast_tangent_solve_threshold=1,
        maximum_attempt_count=8,
        step_config=_step_config(),
    )


@dataclass(frozen=True)
class _RejectLargeStepSolver:
    delegate: object
    load_factor_delta: float

    @property
    def profile(self) -> str:
        return str(getattr(self.delegate, "profile"))

    @property
    def contract_hash(self) -> str:
        return str(getattr(self.delegate, "contract_hash"))

    def solve_at_state(
        self,
        problem,
        free_displacements_m,
        right_hand_side_kn,
        *,
        load_factor,
        solve_id,
    ) -> VectorArcLengthTangentSolve:
        if self.load_factor_delta > 0.5:
            return VectorArcLengthTangentSolve(
                profile=self.profile,
                contract_hash=self.contract_hash,
                contract_pass=False,
                terminal_reason="injected_large_step_rejection",
                solution_free=tuple(np.zeros_like(right_hand_side_kn)),
                receipt={"fallback_count": 0, "regularization_count": 0},
            )
        return getattr(self.delegate, "solve_at_state")(
            problem,
            free_displacements_m,
            right_hand_side_kn,
            load_factor=load_factor,
            solve_id=solve_id,
        )


def _reject_large_step_factory(step_problem):
    return _RejectLargeStepSolver(
        delegate=create_matrix_free_cpu_fgmres_state_tangent_solver(step_problem),
        load_factor_delta=step_problem.load_factor_delta,
    )


def _adaptive_with_reduction():
    return adaptive_stateful_axial_matrix_free_newton_continuation(
        two_element_stateful_steel_chain_problem(),
        config=_adaptive_config(),
        solver_factory=_reject_large_step_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )


def test_adaptive_material_path_reduces_only_after_exact_rollback() -> None:
    problem = two_element_stateful_steel_chain_problem()
    initial = initial_stateful_axial_state(problem)
    initial_bytes = initial.canonical_bytes()
    initial_material_bytes = tuple(
        state.canonical_bytes() for state in initial.material_states
    )
    result = adaptive_stateful_axial_matrix_free_newton_continuation(
        problem,
        config=_adaptive_config(),
        initial_state=initial,
        solver_factory=_reject_large_step_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )
    payload = result.to_dict()

    assert result.status == "ready"
    assert result.terminal_reason == "target_load_factor_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["attempt_count"] == 3
    assert result.metrics["accepted_step_count"] == 2
    assert result.metrics["failed_step_count"] == 1
    assert result.metrics["failed_step_reduction_count"] == 1
    assert result.metrics["fast_step_growth_count"] == 1
    assert result.metrics["accepted_matrix_free_newton_step_count"] == 1
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["residual_and_increment_acceptance_gate"] is True
    assert result.metrics["target_load_factor_reached"] is True
    assert [row.outcome for row in result.attempts] == [
        "rolled_back",
        "committed",
        "committed",
    ]
    assert [row.attempted_step_size for row in result.attempts] == [
        1.0,
        0.5,
        0.5,
    ]
    failed = result.attempts[0].step_result
    assert failed.accepted_state is initial
    assert failed.accepted_state.canonical_bytes() == initial_bytes
    assert (
        tuple(
            state.canonical_bytes() for state in failed.accepted_state.material_states
        )
        == initial_material_bytes
    )
    assert failed.metrics["rollback_exact"] is True
    assert result.final_state.load_factor == 1.0
    assert any(
        before.state_hash != after.state_hash
        for before, after in zip(
            initial.material_states,
            result.final_state.material_states,
            strict=True,
        )
    )
    assert payload["claims"]["adaptive_stateful_axial_matrix_free_newton_path"] is True
    assert payload["claims"]["consistent_matrix_free_newton_step_executed"] is True
    assert payload["claims"]["material_state_commit_rollback"] is True
    assert payload["claims"]["failed_step_reduction_exercised"] is True
    assert payload["claims"]["failed_step_material_state_rollback_exact"] is True
    assert payload["claims"]["source_bound_canonical_checkpoint"] is True
    assert payload["claims"]["arc_length_branch"] is False
    assert payload["claims"]["general_frame_shell_material_newton"] is False
    assert payload["claims"]["rocm_hip_parity"] is False
    assert payload["claims"]["g1_full_building_closure"] is False


def test_failed_attempt_checkpoint_restart_reaches_exact_one_shot_state() -> None:
    problem = two_element_stateful_steel_chain_problem()
    config = _adaptive_config()
    one_shot = adaptive_stateful_axial_matrix_free_newton_continuation(
        problem,
        config=config,
        solver_factory=_reject_large_step_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )
    failed_boundary = one_shot.checkpoints[1]
    raw = failed_boundary.to_bytes()
    loaded = load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
        raw,
        problem,
        config,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )
    restarted = adaptive_stateful_axial_matrix_free_newton_continuation(
        problem,
        config=config,
        checkpoint=loaded,
        solver_factory=_reject_large_step_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )

    assert failed_boundary.accepted_state.load_factor == 0.0
    assert failed_boundary.progress.attempt_count == 1
    assert failed_boundary.progress.failed_step_count == 1
    assert failed_boundary.next_step_size == 0.5
    assert loaded.to_bytes() == raw
    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.metrics["attempt_count"] == one_shot.metrics["attempt_count"]
    assert (
        restarted.metrics["accepted_step_count"]
        == (one_shot.metrics["accepted_step_count"])
    )
    assert (
        restarted.metrics["failed_step_count"]
        == (one_shot.metrics["failed_step_count"])
    )
    assert (
        restarted.metrics["tangent_solve_count"]
        == (one_shot.metrics["tangent_solve_count"])
    )
    assert restarted.final_state.state_hash == one_shot.final_state.state_hash
    assert restarted.final_state.canonical_bytes() == (
        one_shot.final_state.canonical_bytes()
    )
    assert tuple(
        state.canonical_bytes() for state in restarted.final_state.material_states
    ) == tuple(
        state.canonical_bytes() for state in one_shot.final_state.material_states
    )


def test_restart_cannot_reset_the_persisted_attempt_budget() -> None:
    problem = two_element_stateful_steel_chain_problem()
    config = replace(_adaptive_config(), maximum_attempt_count=1)
    first = adaptive_stateful_axial_matrix_free_newton_continuation(
        problem,
        config=config,
        solver_factory=_reject_large_step_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )
    checkpoint = load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
        first.final_checkpoint.to_bytes(),
        problem,
        config,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )
    restarted = adaptive_stateful_axial_matrix_free_newton_continuation(
        problem,
        config=config,
        checkpoint=checkpoint,
        solver_factory=_reject_large_step_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )

    assert first.status == "blocked"
    assert first.terminal_reason == "maximum_attempt_count_exhausted"
    assert first.metrics["attempt_count"] == 1
    assert first.final_checkpoint.next_step_size == 0.5
    assert restarted.status == "blocked"
    assert restarted.terminal_reason == "maximum_attempt_count_exhausted"
    assert restarted.metrics["attempt_count"] == 1
    assert restarted.metrics["run_attempt_count"] == 0
    assert restarted.final_checkpoint.checkpoint_hash == (
        first.final_checkpoint.checkpoint_hash
    )


def test_checkpoint_artifact_roundtrip_is_exact_and_non_overwriting(
    tmp_path: Path,
) -> None:
    problem = two_element_stateful_steel_chain_problem()
    config = _adaptive_config()
    checkpoint = _adaptive_with_reduction().final_checkpoint
    target = tmp_path / "accepted-state-checkpoint.json"

    written = write_stateful_axial_adaptive_matrix_free_checkpoint_artifact(
        checkpoint,
        target,
    )
    loaded = read_stateful_axial_adaptive_matrix_free_checkpoint_artifact(
        written,
        problem,
        config,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )

    assert written.read_bytes() == checkpoint.to_bytes()
    assert loaded.checkpoint_hash == checkpoint.checkpoint_hash
    assert loaded.accepted_state.state_hash == checkpoint.accepted_state.state_hash
    assert loaded.to_bytes() == checkpoint.to_bytes()
    with pytest.raises(
        StatefulAxialAdaptiveMatrixFreeNewtonError,
        match="already exists",
    ):
        write_stateful_axial_adaptive_matrix_free_checkpoint_artifact(
            checkpoint,
            target,
        )
    assert written.read_bytes() == checkpoint.to_bytes()


def test_checkpoint_rejects_tamper_source_drift_and_path_drift() -> None:
    problem = two_element_stateful_steel_chain_problem()
    config = _adaptive_config()
    checkpoint = _adaptive_with_reduction().final_checkpoint
    raw = checkpoint.to_bytes()
    payload = json.loads(raw)
    payload["boundary"]["next_step_size"] = 0.25
    tampered = canonical_json_bytes(payload)

    with pytest.raises(
        StatefulAxialAdaptiveMatrixFreeNewtonError,
        match="checkpoint_hash mismatch",
    ):
        load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
            tampered,
            problem,
            config,
            solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
        )
    with pytest.raises(
        StatefulAxialAdaptiveMatrixFreeNewtonError,
        match="not canonical JSON",
    ):
        load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
            raw + b"\n",
            problem,
            config,
            solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
        )

    modified_material = replace(
        problem.elements[0].material,
        elastic_modulus_mpa=190_000.0,
    )
    modified_problem = replace(
        problem,
        elements=tuple(
            replace(element, material=modified_material) for element in problem.elements
        ),
    )
    with pytest.raises(
        StatefulAxialAdaptiveMatrixFreeNewtonError,
        match="source problem contract mismatch",
    ):
        load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
            raw,
            modified_problem,
            config,
            solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
        )

    changed_config = replace(config, maximum_attempt_count=9)
    with pytest.raises(
        StatefulAxialAdaptiveMatrixFreeNewtonError,
        match="path contract mismatch",
    ):
        load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
            raw,
            problem,
            changed_config,
            solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
        )


@pytest.mark.parametrize(
    "problem_factory",
    (
        two_element_stateful_steel_chain_problem,
        two_element_concrete_damage_chain_problem,
        two_element_composite_section_chain_problem,
        two_element_bilinear_link_chain_problem,
    ),
)
def test_checkpoint_restores_every_bounded_material_state_family(
    problem_factory,
) -> None:
    problem = problem_factory()
    config = _adaptive_config()
    result = adaptive_stateful_axial_matrix_free_newton_continuation(
        problem,
        config=config,
    )
    checkpoint = result.final_checkpoint
    loaded = load_stateful_axial_adaptive_matrix_free_checkpoint_bytes(
        checkpoint.to_bytes(),
        problem,
        config,
    )

    assert result.status == "ready"
    assert checkpoint.schema_version == (
        STATEFUL_AXIAL_ADAPTIVE_MATRIX_FREE_CHECKPOINT_SCHEMA_VERSION
    )
    assert loaded.checkpoint_hash == checkpoint.checkpoint_hash
    assert loaded.accepted_state.canonical_bytes() == (
        checkpoint.accepted_state.canonical_bytes()
    )
    assert tuple(
        state.canonical_bytes() for state in loaded.accepted_state.material_states
    ) == tuple(
        state.canonical_bytes() for state in checkpoint.accepted_state.material_states
    )
    assert any(
        state.state_hash != initial.state_hash
        for state, initial in zip(
            loaded.accepted_state.material_states,
            initial_stateful_axial_state(problem).material_states,
            strict=True,
        )
    )


def test_custom_solver_factory_requires_a_bound_contract_hash() -> None:
    with pytest.raises(
        StatefulAxialAdaptiveMatrixFreeNewtonError,
        match="requires solver_factory_contract_hash",
    ):
        adaptive_stateful_axial_matrix_free_newton_continuation(
            two_element_stateful_steel_chain_problem(),
            config=_adaptive_config(),
            solver_factory=_reject_large_step_factory,
        )
