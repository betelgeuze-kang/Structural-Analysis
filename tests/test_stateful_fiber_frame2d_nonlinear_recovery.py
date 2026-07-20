from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest

from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    physical_3dof_to_canonical_6dof,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_recovery import (
    FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES,
    FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_CLAIM_BOUNDARY,
    FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE,
    FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_CLAIM_BOUNDARY,
    FiberFrameNonlinearRecoveryError,
    create_fiber_frame_nonlinear_engineering_result_ir,
    create_fiber_frame_nonlinear_recovery_operator,
    validate_fiber_frame_nonlinear_engineering_result_manifest,
    validate_fiber_frame_nonlinear_recovery_operator_manifest,
    validate_fiber_frame_nonlinear_recovery_operator_shape,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
    create_fiber_frame_nonlinear_numerical_result_adapter,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.nonlinear_recovery import (
    NonlinearRecoveryError,
    create_nonlinear_recovery_candidate,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY,
)
from tests.test_stateful_fiber_frame2d_nonlinear_terminal_receipt import _artifacts


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _source_force_to_si(plan, source_force) -> np.ndarray:
    canonical = physical_3dof_to_canonical_6dof(plan, source_force)
    values = np.asarray(canonical, dtype=np.float64).reshape((-1, 6)).copy()
    values[:, :3] *= 1000.0
    values[:, 3:] *= 1000.0
    return values.reshape(-1)


@pytest.fixture(scope="module")
def recovered():
    (
        problem,
        path,
        checkpoints,
        plan,
        scaling,
        kinematic,
        material,
        execution_state,
        terminal,
    ) = _artifacts()
    adapter = create_fiber_frame_nonlinear_numerical_result_adapter(
        problem,
        plan,
        scaling,
        checkpoints,
        kinematic,
        material,
        execution_state,
        path,
        terminal,
    )
    operator = create_fiber_frame_nonlinear_recovery_operator(adapter)
    result = create_fiber_frame_nonlinear_engineering_result_ir(
        engineering_result_id="result.fiber-frame.engineering.full-load",
        source_adapter=adapter,
        recovery_operator=operator,
    )
    return {
        "problem": problem,
        "path": path,
        "plan": plan,
        "scaling": scaling,
        "material": material,
        "adapter": adapter,
        "operator": operator,
        "result": result,
    }


@pytest.fixture(scope="module")
def result_manifest(recovered):
    return recovered["result"].to_manifest()


def test_exact_operator_is_the_only_bounded_engineering_authority(
    recovered,
    result_manifest,
) -> None:
    numerical_claims = dict(NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY)
    assert numerical_claims["reaction_authority"] is False
    assert numerical_claims["member_force_authority"] is False
    assert result_manifest["recovery_operator"]["claim_boundary"] == dict(
        FIBER_FRAME_NONLINEAR_RECOVERY_OPERATOR_CLAIM_BOUNDARY
    )
    manifest = result_manifest
    assert manifest["authority"] == dict(
        FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES
    )
    assert manifest["claim_boundary"] == dict(
        FIBER_FRAME_NONLINEAR_ENGINEERING_RESULT_CLAIM_BOUNDARY
    )
    assert manifest["authority"]["reaction"] == "authoritative"
    assert manifest["authority"]["member_force"] == "authoritative"
    assert manifest["authority"]["section_resultant"] == "authoritative"
    assert manifest["authority"]["fiber_strain_stress"] == "authoritative"
    assert manifest["authority"]["engineering_design"] == "not_authoritative"
    assert manifest["authority"]["commercial_use"] == "not_authoritative"


def test_recovered_outputs_match_terminal_engineering_values(recovered) -> None:
    plan = recovered["plan"]
    terminal_assembly = recovered["path"].steps[-1].trial_assembly
    operator = recovered["operator"]

    expected_local = np.asarray(
        [
            row.response.internal_force_local * 1000.0
            for row in terminal_assembly.member_assemblies
        ],
        dtype=np.float64,
    )
    expected_section = np.asarray(
        [
            section_response.resultants * 1000.0
            for member in terminal_assembly.member_assemblies
            for section_response in member.response.section_responses
        ],
        dtype=np.float64,
    )
    expected_fiber_strain = np.asarray(
        [
            value
            for member in terminal_assembly.member_assemblies
            for section_response in member.response.section_responses
            for value in section_response.fiber_strains
        ],
        dtype=np.float64,
    )
    expected_fiber_stress = np.asarray(
        [
            value
            for member in terminal_assembly.member_assemblies
            for section_response in member.response.section_responses
            for value in section_response.fiber_stresses_mpa
        ],
        dtype=np.float64,
    )
    expected_residual = _source_force_to_si(
        plan,
        terminal_assembly.internal_loads_global
        - terminal_assembly.external_loads_global,
    )
    expected_reaction = _source_force_to_si(
        plan,
        terminal_assembly.reactions_global,
    )

    np.testing.assert_allclose(
        operator.array("member_local_end_force_si"),
        expected_local,
        rtol=1.0e-14,
        atol=1.0e-9,
    )
    np.testing.assert_allclose(
        operator.array("section_resultant_si"),
        expected_section,
        rtol=1.0e-14,
        atol=1.0e-9,
    )
    np.testing.assert_array_equal(operator.array("fiber_strain"), expected_fiber_strain)
    np.testing.assert_array_equal(
        operator.array("fiber_stress_mpa"),
        expected_fiber_stress,
    )
    np.testing.assert_allclose(
        operator.array("equilibrium_residual_global_si"),
        expected_residual,
        rtol=1.0e-14,
        atol=1.0e-9,
    )
    np.testing.assert_allclose(
        operator.array("reaction_global_si"),
        expected_reaction,
        rtol=1.0e-14,
        atol=1.0e-9,
    )


def test_order_state_bytes_metrics_and_immutable_arrays_are_bound(recovered) -> None:
    material = recovered["material"]
    adapter = recovered["adapter"]
    operator = recovered["operator"]
    terminal_projection = material.projections[-1]

    assert operator.member_count == 2
    assert operator.integration_point_count == 6
    assert operator.fiber_output_count == 84
    assert operator.fiber_output_order_hash == (
        terminal_projection.receipt.source_identity_hash
    )
    assert operator.terminal_material_state_bundle_hash == (
        terminal_projection.bundle.bundle_hash
    )
    assert operator.state_bytes_exact is True
    assert operator.free_residual_scaled_linf <= (
        adapter.source_binding.solver_residual_tolerance
    )
    for value in (
        operator.element_scatter_scaled_linf,
        operator.local_global_force_scaled_linf,
        operator.section_integration_scaled_linf,
        operator.section_resultant_scaled_linf,
        operator.local_global_work_scaled_abs,
        operator.section_element_work_scaled_abs,
        operator.dissipated_energy_balance_scaled_abs,
        operator.transformation_orthogonality_linf,
    ):
        assert value <= FIBER_FRAME_NONLINEAR_RECOVERY_CONSISTENCY_TOLERANCE
    assert operator.fiber_strain_linf == 0.0
    for descriptor in operator.descriptors:
        array = operator.array(descriptor.name)
        assert array.flags.writeable is False
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_result_manifest_is_strict_descriptor_only_and_cross_bound(
    result_manifest,
) -> None:
    normalized = validate_fiber_frame_nonlinear_engineering_result_manifest(
        result_manifest
    )
    nested = normalized["recovery_operator"]
    assert validate_fiber_frame_nonlinear_recovery_operator_manifest(nested) == nested
    assert normalized["array_bundle_hash"] == nested["array_bundle_hash"]
    assert normalized["artifact_descriptors"] == nested["array_descriptors"]
    assert len(normalized["artifact_descriptors"]) == 21
    encoded = json.dumps(normalized, sort_keys=True)
    assert '"arrays"' not in encoded
    assert '"values"' not in encoded
    assert "global_displacements" not in encoded
    assert '"constituent_state_bytes":' not in encoded


def test_same_exact_source_replays_to_identical_hash_and_bytes(recovered) -> None:
    first = recovered["operator"]
    second = create_fiber_frame_nonlinear_recovery_operator(recovered["adapter"])

    assert second.recovery_operator_hash == first.recovery_operator_hash
    assert second.array_bundle_hash == first.array_bundle_hash
    assert second.descriptors == first.descriptors
    for descriptor in first.descriptors:
        np.testing.assert_array_equal(
            second.array(descriptor.name),
            first.array(descriptor.name),
        )


def test_in_memory_metric_and_array_tampering_fail_closed(recovered) -> None:
    operator = recovered["operator"]
    with pytest.raises(
        FiberFrameNonlinearRecoveryError,
        match="fiber_frame_recovery_consistency_gate_failed",
    ):
        validate_fiber_frame_nonlinear_recovery_operator_shape(
            replace(operator, element_scatter_scaled_linf=1.0)
        )

    with pytest.raises(
        FiberFrameNonlinearRecoveryError,
        match="fiber_frame_recovery_state_bytes_gate_failed",
    ):
        validate_fiber_frame_nonlinear_recovery_operator_shape(
            replace(operator, state_bytes_exact=False)
        )


def test_manifest_descriptor_and_rehashed_cross_binding_tamper_fail_closed(
    result_manifest,
) -> None:
    bad_descriptor = deepcopy(result_manifest["recovery_operator"])
    bad_descriptor["array_descriptors"][0]["byte_length"] += 4
    with pytest.raises(
        FiberFrameNonlinearRecoveryError,
        match="fiber_frame_recovery_manifest_descriptor_invalid",
    ):
        validate_fiber_frame_nonlinear_recovery_operator_manifest(bad_descriptor)

    changed = deepcopy(result_manifest)
    changed["source"]["numerical_result_hash"] = _hash("f")
    changed["engineering_result_hash"] = canonical_hash(
        {
            key: value
            for key, value in changed.items()
            if key != "engineering_result_hash"
        }
    )
    with pytest.raises(
        FiberFrameNonlinearRecoveryError,
        match="fiber_frame_engineering_result_manifest_source_mismatch",
    ):
        validate_fiber_frame_nonlinear_engineering_result_manifest(changed)


def test_generic_candidate_remains_fail_closed_for_adapter_source(recovered) -> None:
    numerical_result = recovered["adapter"].numerical_result
    zeros = np.zeros(numerical_result.dof_count, dtype="<f8")
    dofs = np.arange(numerical_result.dof_count, dtype="<i8").reshape(1, -1)

    with pytest.raises(
        NonlinearRecoveryError,
        match="nonlinear_recovery_source_profile_unsupported",
    ):
        create_nonlinear_recovery_candidate(
            recovery_id="recovery.fiber-frame.generic-blocked",
            nonlinear_result=numerical_result,
            global_external_force_si=zeros,
            global_internal_force_si=zeros,
            element_global_dofs=dofs,
            element_internal_force_si=zeros.reshape(1, -1),
            member_axial_force_si=np.zeros(1, dtype="<f8"),
            recovery_law_receipt_hash=_hash("a"),
        )
