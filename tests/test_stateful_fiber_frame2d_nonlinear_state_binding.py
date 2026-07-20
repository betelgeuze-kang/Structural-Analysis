from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    create_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    create_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_state_binding import (
    FIBER_FRAME_NONLINEAR_STATE_BINDING_AUTHORITY_PROFILE,
    FiberFrameNonlinearStateBindingError,
    _binding_payload,
    _row_payload,
    create_fiber_frame_nonlinear_state_binding,
    create_material_projection_chain_for_kinematic_states,
    validate_fiber_frame_nonlinear_state_binding,
    validate_fiber_frame_nonlinear_state_binding_manifest,
    validate_fiber_frame_nonlinear_state_binding_row,
    validate_fiber_frame_nonlinear_state_binding_shape,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.benchmark import make_two_member_stateful_fiber_l_frame
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64


def _fixture(load_factors=(0.25, 0.5)):
    problem = make_two_member_stateful_fiber_l_frame()
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("N1", "N2", "N3"),
    )
    physical_scaling = create_stateful_fiber_frame2d_physical_equation_scaling(
        problem,
        plan,
    )
    path = run_stateful_fiber_frame2d_load_path(
        problem,
        load_factors,
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    assert path.contract_pass is True
    checkpoint_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        (
            path.initial_checkpoint,
            *(step.accepted_checkpoint for step in path.steps),
        ),
    )
    kinematic_chain = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
    )
    material_chain = create_material_projection_chain_for_kinematic_states(
        problem,
        plan,
        checkpoint_chain,
        kinematic_chain,
    )
    binding = create_fiber_frame_nonlinear_state_binding(
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
    )
    return (
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        binding,
    )


def test_j4_binds_each_material_bundle_to_exact_j3_committed_state() -> None:
    (
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        binding,
    ) = _fixture()

    assert binding.authority_profile == (
        FIBER_FRAME_NONLINEAR_STATE_BINDING_AUTHORITY_PROFILE
    )
    assert binding.checkpoint_chain_hash == checkpoint_chain.chain_hash
    assert binding.kinematic_state_chain_hash == kinematic_chain.chain_hash
    assert binding.material_projection_chain_hash == material_chain.chain_hash
    assert binding.physical_equation_scaling_binding_hash == (
        physical_scaling.binding_hash
    )
    assert binding.execution_topology_plan_hash == plan.plan_hash
    assert binding.state_count == len(checkpoint_chain.checkpoints) == 3
    assert binding.root_kinematic_state_hash == (
        kinematic_chain.root_kinematic_state_hash
    )
    assert binding.terminal_material_state_bundle_hash == (
        material_chain.terminal_material_state_bundle_hash
    )

    for index, (checkpoint, state, projection, row) in enumerate(
        zip(
            checkpoint_chain.checkpoints,
            kinematic_chain.committed_states,
            material_chain.projections,
            binding.rows,
            strict=True,
        )
    ):
        assert row.epoch == row.step_index == index
        assert row.checkpoint_state_hash == checkpoint.state_hash
        assert row.parent_checkpoint_state_hash == checkpoint.parent_state_hash
        assert row.kinematic_state_hash == state.state_hash
        assert row.material_projection_receipt_hash == (projection.receipt.receipt_hash)
        assert row.material_state_bundle_hash == projection.bundle.bundle_hash
        assert row.material_bundle_solver_state_hash == state.state_hash
        assert projection.receipt.solver_state_hash == state.state_hash
        assert projection.bundle.solver_state_hash == state.state_hash
        assert projection.bundle.epoch == state.epoch
        validate_fiber_frame_nonlinear_state_binding_row(row)

    validate_fiber_frame_nonlinear_state_binding(
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        binding,
    )


def test_persisted_checkpoint_chain_replays_identical_j4_binding() -> None:
    (
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        _kinematic_chain,
        _material_chain,
        original,
    ) = _fixture()
    encoded = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
        problem,
        checkpoint_chain,
    )
    restored_checkpoints = load_stateful_fiber_frame2d_checkpoint_chain_bytes(
        encoded,
        problem,
    )
    restored_kinematics = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        restored_checkpoints,
    )
    restored_material = create_material_projection_chain_for_kinematic_states(
        problem,
        plan,
        restored_checkpoints,
        restored_kinematics,
    )
    restored = create_fiber_frame_nonlinear_state_binding(
        problem,
        plan,
        physical_scaling,
        restored_checkpoints,
        restored_kinematics,
        restored_material,
    )

    assert restored_checkpoints.chain_hash == checkpoint_chain.chain_hash
    assert restored.to_manifest() == original.to_manifest()
    assert [row.row_hash for row in restored.rows] == [
        row.row_hash for row in original.rows
    ]


def test_append_preserves_historical_row_hashes_but_changes_outer_binding() -> None:
    *_, short_binding = _fixture((0.25,))
    *_, long_binding = _fixture((0.25, 0.5))

    assert long_binding.state_count == short_binding.state_count + 1
    assert [row.row_hash for row in long_binding.rows[:2]] == [
        row.row_hash for row in short_binding.rows
    ]
    assert long_binding.binding_hash != short_binding.binding_hash
    assert long_binding.terminal_checkpoint_state_hash != (
        short_binding.terminal_checkpoint_state_hash
    )


def test_wrong_solver_state_hash_material_chain_fails_closed() -> None:
    (
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        _material_chain,
        _binding,
    ) = _fixture()
    wrong_hashes = tuple("sha256:" + character * 64 for character in ("7", "8", "9"))
    wrong_material = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=kinematic_chain.model_ir_content_hash,
        execution_plan_hash=kinematic_chain.execution_topology_plan_hash,
        solver_state_hashes=wrong_hashes,
    )

    with pytest.raises(
        FiberFrameNonlinearStateBindingError,
        match="fiber_frame_nonlinear_state_binding_solver_hash_mismatch",
    ):
        create_fiber_frame_nonlinear_state_binding(
            problem,
            plan,
            physical_scaling,
            checkpoint_chain,
            kinematic_chain,
            wrong_material,
        )


def test_wrong_material_plan_hash_fails_before_join() -> None:
    (
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        _material_chain,
        _binding,
    ) = _fixture()
    wrong_material = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=kinematic_chain.model_ir_content_hash,
        execution_plan_hash="sha256:" + "a" * 64,
        solver_state_hashes=kinematic_chain.solver_state_hashes,
    )

    with pytest.raises(
        FiberFrameNonlinearStateBindingError,
        match="fiber_frame_nonlinear_state_binding_model_plan_mismatch",
    ):
        create_fiber_frame_nonlinear_state_binding(
            problem,
            plan,
            physical_scaling,
            checkpoint_chain,
            kinematic_chain,
            wrong_material,
        )


def test_row_and_binding_coherent_tamper_fail_closed() -> None:
    (
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        binding,
    ) = _fixture()
    row = binding.rows[-1]
    changed_row = replace(
        row,
        material_bundle_solver_state_hash="sha256:" + "b" * 64,
    )
    changed_row = replace(
        changed_row,
        row_hash=canonical_hash(_row_payload(changed_row, include_hash=False)),
    )
    with pytest.raises(
        FiberFrameNonlinearStateBindingError,
        match="fiber_frame_nonlinear_state_binding_solver_hash_mismatch",
    ):
        validate_fiber_frame_nonlinear_state_binding_row(changed_row)

    changed_binding = replace(
        binding,
        material_projection_chain_hash="sha256:" + "c" * 64,
    )
    changed_binding = replace(
        changed_binding,
        binding_hash=canonical_hash(
            _binding_payload(changed_binding, include_hash=False)
        ),
    )
    validate_fiber_frame_nonlinear_state_binding_shape(changed_binding)
    with pytest.raises(
        FiberFrameNonlinearStateBindingError,
        match="fiber_frame_nonlinear_state_binding_source_mismatch",
    ):
        validate_fiber_frame_nonlinear_state_binding(
            problem,
            plan,
            physical_scaling,
            checkpoint_chain,
            kinematic_chain,
            material_chain,
            changed_binding,
        )


def test_manifest_is_descriptor_free_non_authoritative_and_fail_closed() -> None:
    *_, binding = _fixture()
    manifest = binding.to_manifest()

    assert validate_fiber_frame_nonlinear_state_binding_manifest(manifest) == manifest
    assert manifest["claim_boundary"]["nonlinear_numerical_result_authority"] is False
    assert manifest["claim_boundary"]["constitutive_transition_replayed"] is False
    assert (
        manifest["claim_boundary"][
            "material_bundle_solver_state_hash_matches_kinematic_state"
        ]
        is True
    )
    assert "state_bytes" not in str(manifest)
    assert "canonical_displacement_si" not in str(manifest)

    promoted = deepcopy(manifest)
    promoted["authority_profile"] = "authoritative_nonlinear_state"
    unsigned = dict(promoted)
    unsigned.pop("binding_hash")
    promoted["binding_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        FiberFrameNonlinearStateBindingError,
        match="fiber_frame_nonlinear_state_binding_authority_invalid",
    ):
        validate_fiber_frame_nonlinear_state_binding_manifest(promoted)

    unknown = deepcopy(manifest)
    unknown["result_authority"] = True
    unsigned = dict(unknown)
    unsigned.pop("binding_hash")
    unknown["binding_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        FiberFrameNonlinearStateBindingError,
        match="fiber_frame_nonlinear_state_binding_manifest_fields_invalid",
    ):
        validate_fiber_frame_nonlinear_state_binding_manifest(unknown)
