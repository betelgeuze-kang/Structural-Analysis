from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_PHYSICAL_DOF_COMPONENTS,
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FIBER_FRAME_FORCE_TO_SI,
    FIBER_FRAME_PHYSICAL_EQUATION_SCALING_CLAIM_BOUNDARY,
    FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_CLAIM_BOUNDARY,
    FIBER_FRAME_SOURCE_UNIT_PROFILE,
    FiberFramePhysicalEquationScalingError,
    _array_descriptor,
    _binding_payload,
    _trace_payload,
    create_stateful_fiber_frame2d_physical_equation_scaling,
    trace_stateful_fiber_frame2d_physical_residual,
    validate_fiber_frame_physical_equation_scaling_against_problem,
    validate_fiber_frame_physical_equation_scaling_array_bytes,
    validate_fiber_frame_physical_equation_scaling_binding,
    validate_fiber_frame_physical_equation_scaling_manifest,
    validate_fiber_frame_physical_residual_trace,
    validate_fiber_frame_physical_residual_trace_array_bytes,
    validate_fiber_frame_physical_residual_trace_manifest,
)
from structural_analysis.benchmark import (
    make_two_element_stateful_fiber_cantilever,
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (
    CHARACTERISTIC_LENGTH_POLICY,
    EQUATION_SCALING_SCHEMA_VERSION,
    REFERENCE_EQUATION_SCOPE,
    REFERENCE_FORCE_POLICY,
    EquationScalingError,
    _scaling_payload as _engine_scaling_payload,
    _source_commitment_payload as _engine_source_commitment_payload,
    validate_equation_scaling_manifest,
)


MODEL_HASH = "sha256:" + "1" * 64
NODE_IDS = ("N1", "N2", "N3")


def _artifacts(problem=None, *, node_ids=NODE_IDS):
    selected = problem or make_two_member_stateful_fiber_l_frame()
    plan = compile_stateful_fiber_frame2d_execution_topology(
        selected,
        model_ir_content_hash=MODEL_HASH,
        node_ids=node_ids,
    )
    binding = create_stateful_fiber_frame2d_physical_equation_scaling(
        selected,
        plan,
    )
    return selected, plan, binding


def _rehash_binding_manifest(manifest: dict) -> dict:
    engine = manifest["engine_v2_equation_scaling"]
    unsigned_engine = dict(engine)
    unsigned_engine.pop("scaling_hash", None)
    engine["scaling_hash"] = canonical_hash(unsigned_engine)
    manifest["bindings"]["engine_equation_scaling_hash"] = engine["scaling_hash"]
    manifest["bindings"]["engine_source_commitment_hash"] = engine["source_commitment"][
        "commitment_hash"
    ]
    unsigned = dict(manifest)
    unsigned.pop("binding_hash", None)
    manifest["binding_hash"] = canonical_hash(unsigned)
    return manifest


def _rehash_trace_manifest(manifest: dict) -> dict:
    unsigned = dict(manifest)
    unsigned.pop("trace_hash", None)
    manifest["trace_hash"] = canonical_hash(unsigned)
    return manifest


def _rehash_engine_scaling(scaling):
    with_source = replace(
        scaling,
        source_commitment_hash=canonical_hash(
            _engine_source_commitment_payload(
                scaling,
                include_commitment_hash=False,
            )
        ),
    )
    return replace(
        with_source,
        scaling_hash=canonical_hash(
            _engine_scaling_payload(with_source, include_scaling_hash=False)
        ),
    )


def _rehash_binding(binding):
    return replace(
        binding,
        binding_hash=canonical_hash(
            _binding_payload(binding, include_binding_hash=False)
        ),
    )


def _trace_from_assembly():
    problem, plan, binding = _artifacts()
    checkpoint = initial_stateful_fiber_frame2d_checkpoint(problem)
    trial_free = np.linspace(-2.0e-5, 3.0e-5, len(problem.free_global_dofs))
    assembly = assemble_stateful_fiber_frame2d(
        problem,
        checkpoint,
        target_load_factor=0.2,
        trial_free_coordinates_m=trial_free,
    )
    source_residual = assembly.internal_loads_global - assembly.external_loads_global
    trace = trace_stateful_fiber_frame2d_physical_residual(
        topology_plan=plan,
        scaling_binding=binding,
        raw_residual_source_3dof=source_residual,
    )
    return problem, plan, binding, assembly, source_residual, trace


def test_binding_reuses_engine_v1_policy_and_normalizes_source_units_to_si() -> None:
    problem, plan, binding = _artifacts()
    scaling = binding.engine_scaling
    expected_length = math.sqrt(73.0) / 3.0

    assert scaling.schema_version == EQUATION_SCALING_SCHEMA_VERSION
    assert scaling.base_plan_hash == plan.plan_hash
    assert scaling.characteristic_length_policy == CHARACTERISTIC_LENGTH_POLICY
    assert scaling.reference_force_policy == REFERENCE_FORCE_POLICY
    assert scaling.reference_equation_scope == REFERENCE_EQUATION_SCOPE
    assert scaling.characteristic_length_m == expected_length
    assert scaling.reference_force_n == 150_000.0
    assert binding.source_unit_profile == FIBER_FRAME_SOURCE_UNIT_PROFILE
    np.testing.assert_array_equal(
        binding.array("node_coordinates_m")[:, :2],
        problem.node_coordinates_m,
    )
    np.testing.assert_array_equal(binding.array("node_coordinates_m")[:, 2], 0.0)
    source_load = plan.array("reference_external_load_physical_6dof")
    np.testing.assert_array_equal(
        binding.array("reference_equation_load_si"),
        FIBER_FRAME_FORCE_TO_SI * source_load,
    )
    expected_divisors = np.empty(plan.physical_dof_count)
    expected_divisors.reshape((-1, 6))[:, :3] = 150_000.0
    expected_divisors.reshape((-1, 6))[:, 3:] = 150_000.0 * expected_length
    np.testing.assert_array_equal(binding.scale_divisors_si, expected_divisors)
    assert all(
        not binding.array(name).flags.writeable
        for name in (
            "node_coordinates_m",
            "reference_equation_load_si",
            "scale_divisors_si",
        )
    )
    with pytest.raises(ValueError):
        binding.scale_divisors_si.setflags(write=True)
    assert "engine_scaling=" not in repr(binding)
    assert "_arrays=" not in repr(binding)

    manifest = binding.to_manifest()
    validate_equation_scaling_manifest(manifest["engine_v2_equation_scaling"])
    assert manifest["claim_boundary"] == dict(
        FIBER_FRAME_PHYSICAL_EQUATION_SCALING_CLAIM_BOUNDARY
    )
    assert manifest["claim_boundary"]["physical_force_moment_si_scaling_bound"]
    assert manifest["claim_boundary"]["solver_convergence_authority"] is False
    assert "converged" not in str(manifest)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        plan,
        binding,
    )


def test_reference_force_uses_free_translations_and_equivalent_moments_only() -> None:
    baseline_problem = make_two_member_stateful_fiber_l_frame()
    with_moment = replace(
        baseline_problem,
        reference_external_loads=((7, -10.0), (8, 60.0)),
    )
    _, _, moment_binding = _artifacts(with_moment)
    expected_force = 60_000.0 / moment_binding.characteristic_length_m
    assert moment_binding.reference_force_n == expected_force

    constrained_load = replace(
        baseline_problem,
        reference_external_loads=((0, 1.0e9), (7, -150.0)),
    )
    _, _, constrained_binding = _artifacts(constrained_load)
    _, _, baseline_binding = _artifacts(baseline_problem)
    assert constrained_binding.reference_force_n == baseline_binding.reference_force_n
    assert (
        constrained_binding.engine_source_commitment_hash
        != baseline_binding.engine_source_commitment_hash
    )
    assert constrained_binding.binding_hash != baseline_binding.binding_hash


def test_binding_identity_tracks_topology_geometry_load_and_explicit_minima() -> None:
    problem, plan, binding = _artifacts()
    repeated = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    assert repeated.to_manifest() == binding.to_manifest()
    assert repeated.binding_hash == binding.binding_hash

    higher_floor = create_stateful_fiber_frame2d_physical_equation_scaling(
        problem,
        plan,
        minimum_reference_force_n=200_000.0,
    )
    assert higher_floor.reference_force_n == 200_000.0
    assert higher_floor.binding_hash != binding.binding_hash

    changed_problem = replace(
        problem,
        reference_external_loads=((7, -151.0),),
    )
    _, changed_plan, changed_binding = _artifacts(changed_problem)
    assert changed_plan.plan_hash != plan.plan_hash
    assert changed_binding.binding_hash != binding.binding_hash
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match="fiber_frame_physical_scaling_topology_mismatch",
    ):
        validate_fiber_frame_physical_equation_scaling_binding(
            binding,
            topology_plan=changed_plan,
        )
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match="fiber_frame_physical_scaling_problem_mismatch",
    ):
        validate_fiber_frame_physical_equation_scaling_against_problem(
            changed_problem,
            plan,
            binding,
        )


def test_fully_constrained_topology_uses_no_solve_path_instead_of_scaling() -> None:
    problem = make_two_element_stateful_fiber_cantilever()
    constrained = replace(
        problem,
        fixed_global_dofs=tuple(range(problem.global_dof_count)),
    )
    plan = compile_stateful_fiber_frame2d_execution_topology(
        constrained,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match="fiber_frame_physical_scaling_free_equation_space_empty",
    ):
        create_stateful_fiber_frame2d_physical_equation_scaling(constrained, plan)


def test_actual_assembly_residual_trace_separates_force_moment_and_scaled_norms() -> (
    None
):
    _, plan, binding, _, source_residual, trace = _trace_from_assembly()
    solver_to_physical = plan.array("solver_to_physical_global_dofs")
    active = plan.array("free_physical_dofs")
    translation = active[active % 6 < 3]
    rotation = active[active % 6 >= 3]

    np.testing.assert_array_equal(trace.raw_residual_source_3dof, source_residual)
    np.testing.assert_array_equal(
        trace.raw_residual_si_6dof[solver_to_physical],
        source_residual * 1000.0,
    )
    np.testing.assert_array_equal(
        trace.raw_residual_si_6dof[plan.array("inactive_physical_dofs")],
        0.0,
    )
    np.testing.assert_array_equal(
        trace.scaled_residual_6dof,
        trace.raw_residual_si_6dof / binding.scale_divisors_si,
    )
    assert trace.raw_translation_linf_n == np.max(
        np.abs(trace.raw_residual_si_6dof[translation])
    )
    assert trace.raw_rotation_linf_nm == np.max(
        np.abs(trace.raw_residual_si_6dof[rotation])
    )
    assert trace.scaled_linf == np.max(np.abs(trace.scaled_residual_6dof[active]))
    assert trace.characteristic_length_m == binding.characteristic_length_m
    assert trace.reference_force_n == binding.reference_force_n
    assert trace.governing_equation in tuple(active)
    assert trace.governing_node_id == plan.node_ids[trace.governing_equation // 6]
    assert (
        trace.governing_dof
        == FIBER_FRAME_PHYSICAL_DOF_COMPONENTS[trace.governing_equation % 6]
    )
    manifest = trace.to_manifest()
    assert manifest["claim_boundary"] == dict(
        FIBER_FRAME_PHYSICAL_RESIDUAL_TRACE_CLAIM_BOUNDARY
    )
    assert "raw_mixed" not in str(manifest)
    assert "converged" not in str(manifest)
    validate_fiber_frame_physical_residual_trace(
        trace,
        topology_plan=plan,
        scaling_binding=binding,
    )


def test_scaled_residual_governing_tie_uses_smallest_free_equation() -> None:
    _, plan, binding = _artifacts()
    source = np.zeros(plan.solver_dof_count)
    first_two_free_solver = np.asarray(plan.array("free_solver_dofs")[:2])
    source[first_two_free_solver] = binding.reference_force_n / 1000.0
    trace = trace_stateful_fiber_frame2d_physical_residual(
        topology_plan=plan,
        scaling_binding=binding,
        raw_residual_source_3dof=source,
    )
    expected = int(plan.array("free_physical_dofs")[0])
    assert trace.scaled_linf == 1.0
    assert trace.governing_equation == expected


def test_scaling_and_trace_external_array_bytes_are_fail_closed() -> None:
    _, _, binding, _, _, trace = _trace_from_assembly()
    for artifact, name, validator in (
        (
            binding,
            "reference_equation_load_si",
            validate_fiber_frame_physical_equation_scaling_array_bytes,
        ),
        (
            trace,
            "raw_residual_si_6dof",
            validate_fiber_frame_physical_residual_trace_array_bytes,
        ),
    ):
        payload = artifact.array(name).tobytes(order="C")
        restored = validator(artifact, name=name, payload=payload)
        np.testing.assert_array_equal(restored, artifact.array(name))
        tampered = bytearray(payload)
        tampered[-1] ^= 1
        with pytest.raises(
            FiberFramePhysicalEquationScalingError,
            match="fiber_frame_physical_scaling_array_bytes_invalid",
        ):
            validator(artifact, name=name, payload=tampered)
        with pytest.raises(
            FiberFramePhysicalEquationScalingError,
            match="fiber_frame_physical_scaling_array_hash_mismatch",
        ):
            validator(artifact, name=name, payload=bytes(tampered))


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda payload: payload["source_units"].__setitem__(
                "force_multiplier_to_si", 1.0
            ),
            "fiber_frame_physical_scaling_source_units_invalid",
        ),
        (
            lambda payload: payload["claim_boundary"].__setitem__("commercial_use", 0),
            "fiber_frame_physical_scaling_claim_boundary_invalid",
        ),
        (
            lambda payload: payload["bindings"].__setitem__(
                "engine_source_commitment_profile", "unversioned"
            ),
            "fiber_frame_physical_scaling_source_profile_invalid",
        ),
        (
            lambda payload: payload["bindings"].__setitem__(
                "problem_contract_hash", "sha256:" + "0" * 64
            ),
            "fiber_frame_physical_scaling_problem_invalid",
        ),
        (
            lambda payload: payload["engine_v2_equation_scaling"][
                "policies"
            ].__setitem__("characteristic_length", "changed.v2"),
            "equation_scaling_schema_invalid",
        ),
        (
            lambda payload: payload["array_descriptors"]["scale_divisors_si"][
                "shape"
            ].__setitem__(0, 6),
            "fiber_frame_physical_scaling_descriptor_invalid",
        ),
    ],
)
def test_coherently_rehashed_scaling_manifest_tamper_fails_closed(
    mutate,
    code: str,
) -> None:
    _, _, binding = _artifacts()
    manifest = deepcopy(binding.to_manifest())
    mutate(manifest)
    _rehash_binding_manifest(manifest)
    with pytest.raises(
        (FiberFramePhysicalEquationScalingError, EquationScalingError),
        match=code,
    ):
        validate_fiber_frame_physical_equation_scaling_manifest(manifest)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda payload: payload["norms"].__setitem__(
                "raw_translation_linf_n",
                payload["norms"]["raw_translation_linf_n"] + 1.0,
            ),
            "fiber_frame_physical_trace_norm_mismatch",
        ),
        (
            lambda payload: payload["governing"].__setitem__("node_id", "BAD"),
            "fiber_frame_physical_trace_governing_mismatch",
        ),
        (
            lambda payload: payload["governing"].__setitem__("equation", True),
            "fiber_frame_physical_scaling_index_invalid",
        ),
        (
            lambda payload: payload["claim_boundary"].__setitem__(
                "numerical_result_authority", True
            ),
            "fiber_frame_physical_scaling_claim_boundary_invalid",
        ),
        (
            lambda payload: payload["vectors"]["raw_residual_si_6dof"].__setitem__(
                0,
                payload["vectors"]["raw_residual_si_6dof"][0] + 1.0,
            ),
            "fiber_frame_physical_trace_descriptor_mismatch",
        ),
        (
            lambda payload: payload["observation"]["active_equations"].append(8),
            "fiber_frame_physical_trace_active_equations_invalid",
        ),
    ],
)
def test_coherently_rehashed_trace_manifest_tamper_fails_closed(
    mutate,
    code: str,
) -> None:
    *_, trace = _trace_from_assembly()
    manifest = deepcopy(trace.to_manifest())
    mutate(manifest)
    _rehash_trace_manifest(manifest)
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match=code,
    ):
        validate_fiber_frame_physical_residual_trace_manifest(manifest)


def test_in_memory_scaling_and_trace_tamper_fail_cross_artifact_replay() -> None:
    _, plan, binding, _, _, trace = _trace_from_assembly()
    wrong_binding = replace(
        binding,
        topology_plan_hash="sha256:" + "9" * 64,
        binding_hash="sha256:" + "8" * 64,
    )
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match="fiber_frame_physical_scaling_base_plan_mismatch",
    ):
        validate_fiber_frame_physical_equation_scaling_binding(wrong_binding)

    mutable_arrays = dict(trace._arrays)
    changed_scaled = np.asarray(trace.scaled_residual_6dof).copy()
    changed_scaled[int(trace.active_equations[0])] += 1.0
    mutable_arrays["scaled_residual_6dof"] = immutable_array(
        changed_scaled, dtype="<f8"
    )
    wrong_trace = replace(trace, _arrays=MappingProxyType(mutable_arrays))
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match="fiber_frame_physical_scaling_descriptor_mismatch",
    ):
        validate_fiber_frame_physical_residual_trace(
            wrong_trace,
            topology_plan=plan,
            scaling_binding=binding,
        )


def test_topology_validation_replays_coherently_rehashed_source_arrays() -> None:
    _, plan, binding = _artifacts()
    changed_coordinates = np.array(binding.array("node_coordinates_m"), copy=True)
    changed_coordinates[0, 0] += 0.25
    immutable_coordinates = immutable_array(changed_coordinates, dtype="<f8")
    changed_descriptor = _array_descriptor(
        "node_coordinates_m",
        immutable_coordinates,
        binding.equation_order_hash,
    )
    descriptors = tuple(
        changed_descriptor if row.name == "node_coordinates_m" else row
        for row in binding.descriptors
    )
    arrays = dict(binding._arrays)
    arrays["node_coordinates_m"] = immutable_coordinates
    scaling = _rehash_engine_scaling(
        replace(
            binding.engine_scaling,
            source_node_coordinates_data_hash=changed_descriptor.data_hash,
            source_node_coordinates_content_hash=changed_descriptor.content_hash,
        )
    )
    tampered = _rehash_binding(
        replace(
            binding,
            engine_scaling=scaling,
            descriptors=descriptors,
            _arrays=MappingProxyType(arrays),
        )
    )

    validate_fiber_frame_physical_equation_scaling_binding(tampered)
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match="fiber_frame_physical_scaling_source_replay_mismatch",
    ):
        validate_fiber_frame_physical_equation_scaling_binding(
            tampered,
            topology_plan=plan,
        )


def test_in_memory_trace_requires_exact_immutable_and_scalar_types() -> None:
    *_, trace = _trace_from_assembly()
    for tampered, code in (
        (
            replace(trace, node_ids=list(trace.node_ids)),
            "fiber_frame_physical_trace_node_order_invalid",
        ),
        (
            replace(trace, active_equations=list(trace.active_equations)),
            "fiber_frame_physical_trace_active_equations_invalid",
        ),
        (
            replace(trace, governing_equation=True),
            "fiber_frame_physical_scaling_index_invalid",
        ),
    ):
        with pytest.raises(FiberFramePhysicalEquationScalingError, match=code):
            validate_fiber_frame_physical_residual_trace(tampered)


@pytest.mark.parametrize(
    "value",
    [
        [False] * 9,
        [0.0] * 8,
        [0.0] * 8 + [math.inf],
        [0.0] * 8 + [math.nan],
    ],
)
def test_residual_input_validation_rejects_bool_shape_and_nonfinite(value) -> None:
    _, plan, binding = _artifacts()
    with pytest.raises(FiberFramePhysicalEquationScalingError):
        trace_stateful_fiber_frame2d_physical_residual(
            topology_plan=plan,
            scaling_binding=binding,
            raw_residual_source_3dof=value,
        )


def test_manifest_roundtrip_is_deterministic_and_strict_about_unknown_keys() -> None:
    _, _, binding, _, _, trace = _trace_from_assembly()
    binding_manifest = binding.to_manifest()
    trace_manifest = trace.to_manifest()
    assert (
        validate_fiber_frame_physical_equation_scaling_manifest(binding_manifest)
        == binding_manifest
    )
    assert validate_fiber_frame_physical_residual_trace_manifest(trace_manifest) == (
        trace_manifest
    )
    assert canonical_hash(_binding_payload(binding, include_binding_hash=False)) == (
        binding.binding_hash
    )
    assert canonical_hash(_trace_payload(trace, include_trace_hash=False)) == (
        trace.trace_hash
    )
    unknown = deepcopy(binding_manifest)
    unknown["backend"] = "cpu"
    with pytest.raises(
        FiberFramePhysicalEquationScalingError,
        match="fiber_frame_physical_scaling_manifest_keys_invalid",
    ):
        validate_fiber_frame_physical_equation_scaling_manifest(unknown)
