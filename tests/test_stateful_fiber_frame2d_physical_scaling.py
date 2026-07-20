from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_scaling import (
    FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE,
    FiberFramePhysicalScalingError,
    _scaling_payload,
    create_fiber_frame_physical_equation_scaling,
    create_fiber_frame_physical_residual_trace,
    validate_fiber_frame_physical_array_bytes,
    validate_fiber_frame_physical_equation_scaling,
    validate_fiber_frame_physical_equation_scaling_against_problem,
    validate_fiber_frame_physical_residual_trace_against_assembly,
    validate_fiber_frame_physical_residual_trace_manifest,
    validate_fiber_frame_physical_scaling_manifest,
)
from structural_analysis.benchmark import make_two_member_stateful_fiber_l_frame
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)


MODEL_HASH = "sha256:" + "1" * 64


def _fixture(problem=None):
    selected = problem or make_two_member_stateful_fiber_l_frame()
    topology = compile_stateful_fiber_frame2d_execution_topology(
        selected,
        model_ir_content_hash=MODEL_HASH,
        node_ids=tuple(
            f"N{index + 1}" for index in range(len(selected.node_coordinates_m))
        ),
    )
    scaling = create_fiber_frame_physical_equation_scaling(selected, topology)
    checkpoint = initial_stateful_fiber_frame2d_checkpoint(selected)
    assembly = assemble_stateful_fiber_frame2d(
        selected,
        checkpoint,
        target_load_factor=0.5,
        trial_free_coordinates_m=np.zeros(len(selected.free_global_dofs)),
    )
    trace = create_fiber_frame_physical_residual_trace(
        selected,
        topology,
        scaling,
        assembly,
    )
    return selected, topology, scaling, assembly, trace


def test_receipt_separates_force_and_moment_equation_scales() -> None:
    problem, topology, scaling, _assembly, _trace = _fixture()
    coordinates = np.asarray(problem.node_coordinates_m, dtype=float)
    expected_length = float(
        np.linalg.norm(np.max(coordinates, axis=0) - np.min(coordinates, axis=0))
    )

    assert scaling.authority_profile == FIBER_FRAME_PHYSICAL_SCALING_AUTHORITY_PROFILE
    assert scaling.topology_plan_hash == topology.plan_hash
    assert scaling.problem_contract_hash == problem.contract_hash
    assert scaling.characteristic_length_m == pytest.approx(expected_length)
    assert scaling.moment_reference_kn_m == pytest.approx(
        scaling.force_reference_kn * expected_length
    )
    physical = scaling.array("physical_equation_scale")
    for node in range(topology.node_count):
        assert physical[6 * node] == pytest.approx(1.0 / scaling.force_reference_kn)
        assert physical[6 * node + 1] == pytest.approx(1.0 / scaling.force_reference_kn)
        np.testing.assert_array_equal(physical[6 * node + 2 : 6 * node + 5], 0.0)
        assert physical[6 * node + 5] == pytest.approx(
            1.0 / scaling.moment_reference_kn_m
        )
    np.testing.assert_array_equal(
        scaling.array("solver_equation_scale"),
        physical[topology.array("solver_to_physical_global_dofs")],
    )
    np.testing.assert_array_equal(
        scaling.array("reference_load_scaled_6dof"),
        physical * scaling.array("reference_load_physical_6dof"),
    )
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology,
        scaling,
    )


def test_residual_trace_retains_raw_translation_rotation_and_scaled_norms() -> None:
    problem, topology, scaling, assembly, trace = _fixture()
    solver_residual = assembly.internal_loads_global - assembly.external_loads_global
    physical_residual = np.zeros(topology.physical_dof_count)
    physical_residual[topology.array("solver_to_physical_global_dofs")] = (
        solver_residual
    )
    free_physical = topology.array("free_physical_dofs").astype(int)
    free_translation = [dof for dof in free_physical if dof % 6 in (0, 1)]
    free_rotation = [dof for dof in free_physical if dof % 6 == 5]
    expected_scaled = np.zeros(topology.physical_dof_count)
    expected_scaled[free_physical] = (
        physical_residual[free_physical]
        * scaling.array("physical_equation_scale")[free_physical]
    )

    assert trace.raw_translation_linf_kn == pytest.approx(
        np.linalg.norm(physical_residual[free_translation], ord=np.inf)
    )
    assert trace.raw_rotation_linf_kn_m == pytest.approx(
        np.linalg.norm(physical_residual[free_rotation], ord=np.inf)
    )
    assert trace.scaled_linf == pytest.approx(
        np.linalg.norm(expected_scaled[free_physical], ord=np.inf)
    )
    assert trace.scaled_l2 == pytest.approx(
        np.linalg.norm(expected_scaled[free_physical], ord=2)
    )
    np.testing.assert_array_equal(
        trace.array("physical_residual_6dof"), physical_residual
    )
    np.testing.assert_array_equal(
        trace.array("scaled_free_residual_6dof"), expected_scaled
    )
    np.testing.assert_array_equal(
        trace.array("physical_residual_solver_order"), solver_residual
    )
    np.testing.assert_allclose(
        trace.array("generalized_residual_solver_free"),
        assembly.residual_kn,
        rtol=0.0,
        atol=1.0e-12,
    )
    assert trace.governing_component in {"UX", "UY", "RZ"}
    assert trace.governing_node_index == trace.governing_physical_dof // 6
    validate_fiber_frame_physical_residual_trace_against_assembly(
        problem,
        topology,
        scaling,
        assembly,
        trace,
    )


def test_pure_moment_reference_derives_force_scale_from_characteristic_length() -> None:
    base = make_two_member_stateful_fiber_l_frame()
    moment_dof = 3 * (len(base.node_coordinates_m) - 1) + 2
    problem = replace(base, reference_external_loads=((moment_dof, 12.0),))
    topology = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
    )
    scaling = create_fiber_frame_physical_equation_scaling(problem, topology)

    assert scaling.force_reference_kn == pytest.approx(
        max(12.0 / scaling.characteristic_length_m, 1.0)
    )
    assert scaling.moment_reference_kn_m == pytest.approx(
        scaling.force_reference_kn * scaling.characteristic_length_m
    )


def test_geometry_load_and_topology_changes_are_identity_visible() -> None:
    problem, topology, scaling, _assembly, _trace = _fixture()
    moved_coordinates = list(problem.node_coordinates_m)
    x, y = moved_coordinates[-1]
    moved_coordinates[-1] = (x + 0.25, y)
    moved_members = []
    moved_array = np.asarray(moved_coordinates, dtype=float)
    for member in problem.members:
        length = float(
            np.linalg.norm(moved_array[member.node_j] - moved_array[member.node_i])
        )
        moved_members.append(
            replace(member, element=replace(member.element, length_m=length))
        )
    moved = replace(
        problem,
        node_coordinates_m=tuple(moved_coordinates),
        members=tuple(moved_members),
    )
    moved_topology = compile_stateful_fiber_frame2d_execution_topology(
        moved,
        model_ir_content_hash=MODEL_HASH,
    )
    moved_scaling = create_fiber_frame_physical_equation_scaling(moved, moved_topology)
    changed_load = replace(
        problem,
        reference_external_loads=tuple(
            (dof, 2.0 * value) for dof, value in problem.reference_external_loads
        ),
    )
    load_topology = compile_stateful_fiber_frame2d_execution_topology(
        changed_load,
        model_ir_content_hash=MODEL_HASH,
    )
    load_scaling = create_fiber_frame_physical_equation_scaling(
        changed_load,
        load_topology,
    )

    assert scaling.characteristic_length_source_hash != (
        moved_scaling.characteristic_length_source_hash
    )
    assert scaling.scaling_hash != moved_scaling.scaling_hash
    assert scaling.scaling_hash != load_scaling.scaling_hash
    with pytest.raises(
        FiberFramePhysicalScalingError,
        match="fiber_frame_physical_scaling_topology_mismatch",
    ):
        validate_fiber_frame_physical_equation_scaling_against_problem(
            changed_load,
            load_topology,
            scaling,
        )


def test_manifests_are_deterministic_descriptor_only_and_non_authoritative() -> None:
    problem, topology, scaling, assembly, trace = _fixture()
    scaling_replay = create_fiber_frame_physical_equation_scaling(problem, topology)
    trace_replay = create_fiber_frame_physical_residual_trace(
        problem,
        topology,
        scaling_replay,
        assembly,
    )

    assert scaling.to_manifest() == scaling_replay.to_manifest()
    assert trace.to_manifest() == trace_replay.to_manifest()
    assert validate_fiber_frame_physical_scaling_manifest(scaling.to_manifest()) == (
        scaling.to_manifest()
    )
    assert (
        validate_fiber_frame_physical_residual_trace_manifest(trace.to_manifest())
        == trace.to_manifest()
    )
    assert (
        scaling.to_manifest()["claim_boundary"]["solver_convergence_authority"] is False
    )
    assert trace.to_manifest()["claim_boundary"]["numerical_result_authority"] is False
    assert "state_bytes" not in str(scaling.to_manifest())
    assert "state_bytes" not in str(trace.to_manifest())


def test_external_array_bytes_and_retained_array_tamper_fail_closed() -> None:
    _problem, _topology, scaling, _assembly, _trace = _fixture()
    name = "physical_equation_scale"
    payload = scaling.array(name).tobytes(order="C")
    restored = validate_fiber_frame_physical_array_bytes(
        scaling.descriptors,
        name=name,
        payload=payload,
    )
    np.testing.assert_array_equal(restored, scaling.array(name))

    tampered = bytearray(payload)
    tampered[-1] ^= 1
    with pytest.raises(
        FiberFramePhysicalScalingError,
        match="fiber_frame_physical_array_bytes_invalid",
    ):
        validate_fiber_frame_physical_array_bytes(
            scaling.descriptors,
            name=name,
            payload=tampered,
        )
    with pytest.raises(
        FiberFramePhysicalScalingError,
        match="fiber_frame_physical_array_hash_mismatch",
    ):
        validate_fiber_frame_physical_array_bytes(
            scaling.descriptors,
            name=name,
            payload=bytes(tampered),
        )

    arrays = dict(scaling._arrays)
    changed = scaling.array(name).copy()
    changed[0] *= 2.0
    arrays[name] = immutable_array(changed, dtype="<f8")
    changed_receipt = replace(scaling, _arrays=MappingProxyType(arrays))
    with pytest.raises(
        FiberFramePhysicalScalingError,
        match="fiber_frame_physical_descriptor_mismatch",
    ):
        validate_fiber_frame_physical_equation_scaling(changed_receipt)


def test_object_and_manifest_authority_promotion_fail_closed() -> None:
    _problem, _topology, scaling, _assembly, trace = _fixture()
    promoted = replace(
        scaling,
        authority_profile="authoritative_nonlinear_convergence_scaling",
    )
    with pytest.raises(
        FiberFramePhysicalScalingError,
        match="fiber_frame_physical_scaling_authority_invalid",
    ):
        validate_fiber_frame_physical_equation_scaling(promoted)

    manifest = deepcopy(trace.to_manifest())
    manifest["authority_profile"] = "authoritative_nonlinear_result"
    unsigned = dict(manifest)
    unsigned.pop("trace_hash")
    manifest["trace_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        FiberFramePhysicalScalingError,
        match="fiber_frame_physical_manifest_authority_invalid",
    ):
        validate_fiber_frame_physical_residual_trace_manifest(manifest)


def test_coherently_rehashed_scaling_source_substitution_fails_replay() -> None:
    problem, topology, scaling, _assembly, _trace = _fixture()
    changed = replace(
        scaling,
        characteristic_length_source_hash="sha256:" + "9" * 64,
    )
    changed = replace(
        changed,
        scaling_hash=canonical_hash(_scaling_payload(changed, include_hash=False)),
    )
    validate_fiber_frame_physical_equation_scaling(changed)
    with pytest.raises(
        FiberFramePhysicalScalingError,
        match="fiber_frame_physical_scaling_source_replay_mismatch",
    ):
        validate_fiber_frame_physical_equation_scaling_against_problem(
            problem,
            topology,
            changed,
        )
