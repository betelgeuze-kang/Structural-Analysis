from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE,
    FIBER_FRAME_KINEMATIC_BINDING_DECISION,
    FiberFrameExecutionTopologyError,
    _plan_payload,
    canonical_6dof_to_physical_3dof,
    compile_stateful_fiber_frame2d_execution_topology,
    physical_3dof_to_canonical_6dof,
    physical_3dof_to_solver_generalized,
    solver_generalized_to_physical_3dof,
    validate_fiber_frame_execution_topology_against_problem,
    validate_fiber_frame_execution_topology_array_bytes,
    validate_fiber_frame_execution_topology_manifest,
    validate_fiber_frame_execution_topology_plan,
)
from structural_analysis.benchmark import (
    make_two_element_stateful_fiber_cantilever,
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)


MODEL_HASH = "sha256:" + "1" * 64
NODE_IDS = ("N1", "N2", "N3")


def _plan(problem=None, *, node_ids=NODE_IDS):
    selected = problem or make_two_member_stateful_fiber_l_frame()
    return selected, compile_stateful_fiber_frame2d_execution_topology(
        selected,
        model_ir_content_hash=MODEL_HASH,
        node_ids=node_ids,
    )


def _mapped_solver_dofs(node_count: int) -> np.ndarray:
    return np.asarray(
        [6 * node + component for node in range(node_count) for component in (0, 1, 5)],
        dtype=np.int32,
    )


def _inactive_dofs(node_count: int) -> np.ndarray:
    return np.asarray(
        [6 * node + component for node in range(node_count) for component in (2, 3, 4)],
        dtype=np.int32,
    )


def test_compile_maps_three_dof_frame_into_canonical_six_dof_topology() -> None:
    problem, plan = _plan()
    solver_to_physical = _mapped_solver_dofs(plan.node_count)

    assert plan.authority_profile == FIBER_FRAME_EXECUTION_TOPOLOGY_AUTHORITY_PROFILE
    assert plan.kinematic_binding_decision == FIBER_FRAME_KINEMATIC_BINDING_DECISION
    assert plan.node_ids == NODE_IDS
    assert plan.member_ids == tuple(member.member_id for member in problem.members)
    assert plan.node_count == len(problem.node_coordinates_m)
    assert plan.member_count == len(problem.members)
    assert plan.physical_dof_count == 6 * plan.node_count
    assert plan.solver_dof_count == problem.global_dof_count
    np.testing.assert_array_equal(
        plan.array("node_dof_indices"),
        np.arange(plan.physical_dof_count, dtype=np.int32).reshape(
            plan.node_count,
            6,
        ),
    )
    np.testing.assert_array_equal(
        plan.array("solver_to_physical_global_dofs"),
        solver_to_physical,
    )
    np.testing.assert_array_equal(
        plan.array("inactive_physical_dofs"),
        _inactive_dofs(plan.node_count),
    )
    np.testing.assert_array_equal(
        plan.array("authored_fixed_physical_dofs"),
        solver_to_physical[np.asarray(problem.fixed_global_dofs, dtype=np.int32)],
    )
    np.testing.assert_array_equal(
        plan.array("free_physical_dofs"),
        solver_to_physical[np.asarray(problem.free_global_dofs, dtype=np.int32)],
    )
    assert plan.array("member_physical_global_dofs").shape == (
        plan.member_count,
        12,
    )
    assert plan.array("member_active_physical_dofs").shape == (
        plan.member_count,
        6,
    )
    assert plan.array("member_solver_global_dofs").shape == (
        plan.member_count,
        6,
    )
    np.testing.assert_array_equal(
        plan.array("member_active_physical_dofs"),
        solver_to_physical[plan.array("member_solver_global_dofs")],
    )
    physical_load = plan.array("reference_external_load_physical_6dof")
    np.testing.assert_array_equal(
        physical_load[solver_to_physical],
        problem.reference_external_load_vector(),
    )
    np.testing.assert_array_equal(
        physical_load[plan.array("inactive_physical_dofs")],
        0.0,
    )
    assert all(
        not plan.array(name).flags.writeable
        for name, _ in (
            (descriptor.name, descriptor.dtype) for descriptor in plan.descriptors
        )
    )
    validate_fiber_frame_execution_topology_against_problem(problem, plan)


def test_solver_coordinate_scaling_matches_current_newton_coordinate_transform() -> (
    None
):
    problem, plan = _plan()
    scaling = plan.solver_coordinate_scaling
    physical_from_generalized = scaling.array("physical_from_generalized_scale")
    generalized_from_physical = scaling.array("generalized_from_physical_scale")

    np.testing.assert_array_equal(physical_from_generalized[0::3], 1.0)
    np.testing.assert_array_equal(physical_from_generalized[1::3], 1.0)
    np.testing.assert_array_equal(
        physical_from_generalized[2::3],
        1.0 / problem.rotation_coordinate_scale_m,
    )
    np.testing.assert_array_equal(generalized_from_physical[0::3], 1.0)
    np.testing.assert_array_equal(generalized_from_physical[1::3], 1.0)
    np.testing.assert_array_equal(
        generalized_from_physical[2::3],
        problem.rotation_coordinate_scale_m,
    )
    np.testing.assert_array_equal(
        scaling.array("reference_load_generalized_solver_order"),
        physical_from_generalized * problem.reference_external_load_vector(),
    )
    assert "r_generalized=physical_from_generalized_scale*r_physical" in str(
        scaling.to_manifest()
    )
    assert "K_generalized=S*K_physical*S" in str(scaling.to_manifest())


def test_physical_generalized_and_canonical_coordinate_roundtrip_is_exact() -> None:
    _, plan = _plan()
    generalized = np.linspace(-0.09, 0.12, plan.solver_dof_count)
    physical = solver_generalized_to_physical_3dof(plan, generalized)
    canonical = physical_3dof_to_canonical_6dof(plan, physical)
    gathered = canonical_6dof_to_physical_3dof(plan, canonical)
    generalized_roundtrip = physical_3dof_to_solver_generalized(plan, gathered)

    np.testing.assert_array_equal(gathered, physical)
    np.testing.assert_allclose(
        generalized_roundtrip, generalized, rtol=0.0, atol=2.0e-17
    )
    np.testing.assert_array_equal(
        canonical[plan.array("inactive_physical_dofs")],
        0.0,
    )
    invalid = canonical.copy()
    invalid[int(plan.array("inactive_physical_dofs")[0])] = 1.0e-12
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_inactive_coordinate_nonzero",
    ):
        canonical_6dof_to_physical_3dof(plan, invalid)


def test_sparse_pattern_has_diagonal_and_active_member_coupling_only() -> None:
    _, plan = _plan()
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    inactive = set(int(value) for value in plan.array("inactive_physical_dofs"))

    for row in range(plan.physical_dof_count):
        row_columns = columns[int(row_ptr[row]) : int(row_ptr[row + 1])]
        assert row in row_columns
        assert np.all(row_columns[1:] > row_columns[:-1])
        if row in inactive:
            np.testing.assert_array_equal(row_columns, [row])
    for active_row in plan.array("member_active_physical_dofs"):
        coupled = set(int(value) for value in active_row)
        for row in coupled:
            row_columns = set(
                int(value)
                for value in columns[int(row_ptr[row]) : int(row_ptr[row + 1])]
            )
            assert coupled.issubset(row_columns)


def test_replay_is_deterministic_and_manifest_is_descriptor_only() -> None:
    problem, first = _plan()
    second = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    manifest = first.to_manifest()

    assert first.to_manifest() == second.to_manifest()
    assert first.plan_hash == second.plan_hash
    for name in (descriptor.name for descriptor in first.descriptors):
        np.testing.assert_array_equal(first.array(name), second.array(name))
    assert validate_fiber_frame_execution_topology_manifest(manifest) == manifest
    assert "stateless_linear_elastic" not in str(manifest)
    assert "structural-analysis-state-ir.v1" not in str(manifest)
    assert manifest["claim_boundary"]["physical_equation_scaling_bound"] is False
    assert manifest["claim_boundary"]["nonlinear_state_history_bound"] is False
    assert "node_coordinates_xy_m" in str(manifest)
    assert "state_bytes" not in str(manifest)


def test_rotation_load_member_and_entity_changes_are_identity_visible() -> None:
    problem, baseline = _plan()
    changed_rotation = replace(
        problem,
        rotation_coordinate_scale_m=2.0 * problem.rotation_coordinate_scale_m,
    )
    rotation_plan = compile_stateful_fiber_frame2d_execution_topology(
        changed_rotation,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    changed_load = replace(
        problem,
        reference_external_loads=tuple(
            (dof, 1.5 * value) for dof, value in problem.reference_external_loads
        ),
    )
    load_plan = compile_stateful_fiber_frame2d_execution_topology(
        changed_load,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    reordered_problem = replace(problem, members=tuple(reversed(problem.members)))
    reordered_plan = compile_stateful_fiber_frame2d_execution_topology(
        reordered_problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    renamed_plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=("A", "B", "C"),
    )

    assert baseline.topology_hash == rotation_plan.topology_hash
    assert baseline.solver_coordinate_scaling_hash != (
        rotation_plan.solver_coordinate_scaling_hash
    )
    assert baseline.plan_hash != rotation_plan.plan_hash
    assert baseline.topology_hash == load_plan.topology_hash
    assert baseline.numeric_buffer_hash != load_plan.numeric_buffer_hash
    assert baseline.plan_hash != load_plan.plan_hash
    assert baseline.member_ids == tuple(reversed(reordered_plan.member_ids))
    assert baseline.topology_hash != reordered_plan.topology_hash
    assert baseline.entity_mapping_hash != reordered_plan.entity_mapping_hash
    assert baseline.plan_hash != reordered_plan.plan_hash
    assert baseline.topology_hash == renamed_plan.topology_hash
    assert baseline.entity_mapping_hash != renamed_plan.entity_mapping_hash
    assert baseline.plan_hash != renamed_plan.plan_hash


def test_external_array_bytes_are_hash_and_length_checked() -> None:
    _, plan = _plan()
    name = "member_active_physical_dofs"
    payload = plan.array(name).tobytes(order="C")
    restored = validate_fiber_frame_execution_topology_array_bytes(
        plan,
        name=name,
        payload=payload,
    )
    np.testing.assert_array_equal(restored, plan.array(name))

    tampered = bytearray(payload)
    tampered[-1] ^= 1
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_array_bytes_invalid",
    ):
        validate_fiber_frame_execution_topology_array_bytes(
            plan,
            name=name,
            payload=tampered,
        )
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_array_hash_mismatch",
    ):
        validate_fiber_frame_execution_topology_array_bytes(
            plan,
            name=name,
            payload=bytes(tampered),
        )


def test_object_and_manifest_authority_tamper_fail_closed() -> None:
    problem, plan = _plan()
    promoted = replace(
        plan,
        authority_profile="authoritative_nonlinear_execution_plan",
    )
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_authority_profile_invalid",
    ):
        validate_fiber_frame_execution_topology_plan(promoted)

    arrays = dict(plan._arrays)
    changed = plan.array("solver_to_physical_global_dofs").copy()
    changed[0], changed[1] = changed[1], changed[0]
    arrays["solver_to_physical_global_dofs"] = immutable_array(changed, dtype="<i4")
    tampered_arrays = replace(plan, _arrays=MappingProxyType(arrays))
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_descriptor_mismatch",
    ):
        validate_fiber_frame_execution_topology_plan(tampered_arrays)

    changed_source = replace(
        plan,
        source_identity_hash="sha256:" + "9" * 64,
    )
    coherently_rehashed = replace(
        changed_source,
        plan_hash=canonical_hash(
            _plan_payload(changed_source, include_plan_hash=False)
        ),
    )
    validate_fiber_frame_execution_topology_plan(coherently_rehashed)
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_source_identity_mismatch",
    ):
        validate_fiber_frame_execution_topology_against_problem(
            problem,
            coherently_rehashed,
        )

    manifest = deepcopy(plan.to_manifest())
    manifest["authority_profile"] = "authoritative_nonlinear_execution_plan"
    unsigned = dict(manifest)
    unsigned.pop("plan_hash")
    manifest["plan_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_authority_profile_invalid",
    ):
        validate_fiber_frame_execution_topology_manifest(manifest)


def test_coherently_rehashed_case_and_member_identity_tamper_fail_source_replay() -> (
    None
):
    problem, plan = _plan()

    changed_case = replace(plan, case_id="other-case")
    changed_case = replace(
        changed_case,
        plan_hash=canonical_hash(_plan_payload(changed_case, include_plan_hash=False)),
    )
    validate_fiber_frame_execution_topology_plan(changed_case)
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_case_id_mismatch",
    ):
        validate_fiber_frame_execution_topology_against_problem(
            problem,
            changed_case,
        )

    changed_members = replace(plan, member_ids=("M.X", "M.Y"))
    changed_members = replace(
        changed_members,
        plan_hash=canonical_hash(
            _plan_payload(changed_members, include_plan_hash=False)
        ),
    )
    validate_fiber_frame_execution_topology_plan(changed_members)
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_member_ids_mismatch",
    ):
        validate_fiber_frame_execution_topology_against_problem(
            problem,
            changed_members,
        )


def test_invalid_node_identity_and_wrong_problem_fail_closed() -> None:
    problem = make_two_member_stateful_fiber_l_frame()
    for invalid in (("N1", "N2"), ("N1", "N1", "N3"), ("N1", "bad id", "N3")):
        with pytest.raises(FiberFrameExecutionTopologyError):
            compile_stateful_fiber_frame2d_execution_topology(
                problem,
                model_ir_content_hash=MODEL_HASH,
                node_ids=invalid,
            )

    _, plan = _plan(problem)
    other = make_two_element_stateful_fiber_cantilever()
    with pytest.raises(
        FiberFrameExecutionTopologyError,
        match="fiber_frame_topology_problem_contract_mismatch",
    ):
        validate_fiber_frame_execution_topology_against_problem(other, plan)
