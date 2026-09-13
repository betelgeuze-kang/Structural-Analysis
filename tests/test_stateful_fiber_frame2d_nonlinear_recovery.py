from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly import (
    stateful_fiber_frame2d_nonlinear_recovery as recovery_module,
)
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
    validate_fiber_frame_nonlinear_engineering_result_ir,
    validate_fiber_frame_nonlinear_engineering_result_manifest,
    validate_fiber_frame_nonlinear_recovery_operator,
    validate_fiber_frame_nonlinear_recovery_operator_manifest,
    validate_fiber_frame_nonlinear_recovery_operator_shape,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
    FiberFrameNonlinearResultAdapterError,
    create_fiber_frame_nonlinear_numerical_result_adapter,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    FiberFrameNonlinearTerminalReceiptError,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.nonlinear_recovery import (
    NonlinearRecoveryError,
    create_nonlinear_recovery_candidate,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY,
)
from structural_analysis.io.neutral.loader import load_neutral_json
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


def test_terminal_replay_uses_original_coordinates_after_physical_scaling() -> None:
    model = load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    model.sections[0]["width_m"] = 0.401
    model.loads[0]["components"]["FY"] = -1.0
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    compiled, unsupported, _ = public_api._compile(model)
    assert compiled is not None and unsupported == []
    execution = public_api._run_load_path(
        compiled, config, restart_checkpoint_chain=None
    )
    assert execution.path.contract_pass is True
    authority = public_api._create_authority_artifacts(
        model, compiled, execution, config
    )
    operator = authority.engineering_result._recovery_operator
    assert operator.state_bytes_exact is True
    physical_witness = np.float64(float.fromhex("-0x1.7769c79c3070ep-16"))
    roundtrip_witness = (physical_witness * np.float64(3.0)) * np.float64(1.0 / 3.0)
    assert abs(physical_witness - roundtrip_witness) == abs(
        np.spacing(physical_witness)
    )
    np.testing.assert_array_equal(
        authority.adapter.numerical_result.displacement_global_si,
        physical_3dof_to_canonical_6dof(
            authority.adapter.source_binding._topology_plan,
            execution.path.final_checkpoint.global_displacements,
        ),
    )
    np.testing.assert_array_equal(
        operator.array("member_local_end_force_si"),
        np.asarray(
            [
                row.response.internal_force_local * 1000.0
                for row in execution.path.steps[-1].trial_assembly.member_assemblies
            ]
        ),
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


def _invoke_recovery_entry(entry, recovered, *, adapter=None, operator=None):
    source = recovered["adapter"] if adapter is None else adapter
    retained = recovered["operator"] if operator is None else operator
    result = recovered["result"]
    if entry == "create_operator":
        return create_fiber_frame_nonlinear_recovery_operator(source)
    if entry in ("create_engineering", "create_with_operator"):
        return create_fiber_frame_nonlinear_engineering_result_ir(
            engineering_result_id=result.engineering_result_id,
            source_adapter=source,
            recovery_operator=retained if entry == "create_with_operator" else None,
        )
    if entry == "validate_operator":
        return validate_fiber_frame_nonlinear_recovery_operator(retained)
    if entry == "validate_engineering":
        return validate_fiber_frame_nonlinear_engineering_result_ir(result)
    if entry == "operator_manifest":
        return retained.to_manifest()
    if entry == "engineering_manifest":
        return result.to_manifest()
    raise AssertionError(f"Unknown test entry: {entry}")


@pytest.mark.parametrize(
    "entry",
    (
        "create_operator",
        "create_engineering",
        "create_with_operator",
        "validate_operator",
        "validate_engineering",
        "operator_manifest",
        "engineering_manifest",
    ),
)
def test_each_public_recovery_entry_checks_source_and_engineering_replay_once(
    recovered, monkeypatch, entry
) -> None:
    # Count real entry boundaries, without replacing physical checks with stubs.
    # A full adapter validation may itself replay J5 more than once internally.
    calls = {"adapter": 0, "engineering_replay": 0}
    validate_adapter = (
        recovery_module.validate_fiber_frame_nonlinear_numerical_result_adapter
    )
    replay_engineering = recovery_module._replay_terminal_engineering_outputs

    def counted_adapter(source):
        calls["adapter"] += 1
        return validate_adapter(source)

    def counted_replay(source):
        calls["engineering_replay"] += 1
        return replay_engineering(source)

    monkeypatch.setattr(
        recovery_module,
        "validate_fiber_frame_nonlinear_numerical_result_adapter",
        counted_adapter,
    )
    monkeypatch.setattr(
        recovery_module, "_replay_terminal_engineering_outputs", counted_replay
    )
    _invoke_recovery_entry(entry, recovered)
    assert calls == {"adapter": 1, "engineering_replay": 1}


def test_direct_and_supplied_operator_creation_preserve_all_artifact_bytes(
    recovered,
) -> None:
    direct = _invoke_recovery_entry("create_engineering", recovered)
    supplied = _invoke_recovery_entry("create_with_operator", recovered)
    original = recovered["result"]
    for result in (direct, supplied):
        assert result.engineering_result_hash == original.engineering_result_hash
        assert result.recovery_operator_hash == original.recovery_operator_hash
        assert result.array_bundle_hash == original.array_bundle_hash
        assert result.descriptors == original.descriptors
        for descriptor in original.descriptors:
            assert result.artifact(descriptor.name).tobytes(order="C") == (
                original.artifact(descriptor.name).tobytes(order="C")
            )


@pytest.mark.parametrize("entry", ("create_with_operator", "validate_engineering"))
def test_equal_hash_adapter_clone_cannot_replace_exact_retained_source(
    recovered, entry
) -> None:
    # Equal logical identities do not authorize exchanging the retained instance.
    clone = replace(recovered["adapter"])
    assert clone is not recovered["adapter"]
    assert clone.adapter_hash == recovered["adapter"].adapter_hash
    operator = replace(recovered["operator"], _source_adapter=clone)
    with pytest.raises(
        FiberFrameNonlinearRecoveryError,
        match="fiber_frame_engineering_result_source_identity_mismatch",
    ):
        if entry == "create_with_operator":
            _invoke_recovery_entry(entry, recovered, operator=operator)
        else:
            validate_fiber_frame_nonlinear_engineering_result_ir(
                replace(recovered["result"], _recovery_operator=operator)
            )


@pytest.fixture(scope="module")
def rehashed_one_ulp_operator(recovered, result_manifest):
    # Build a self-consistent artifact alteration using the serialized contracts.
    # This must pass shape/hash validation, yet fail independent source replay.
    operator = recovered["operator"]
    name = "fiber_stress_mpa"
    changed = np.array(operator.array(name), copy=True)
    changed[0] = np.nextafter(changed[0], np.inf)
    changed = immutable_array(changed, dtype="<f8")
    assert changed.tobytes() != operator.array(name).tobytes()
    descriptors = []
    for descriptor in operator.descriptors:
        if descriptor.name == name:
            metadata = descriptor.to_dict()
            metadata.pop("content_hash")
            metadata["data_hash"] = array_data_hash(changed)
            descriptor = replace(
                descriptor,
                data_hash=metadata["data_hash"],
                content_hash=canonical_hash(metadata),
            )
        descriptors.append(descriptor)
    manifest = deepcopy(result_manifest["recovery_operator"])
    manifest["array_descriptors"] = [row.to_dict() for row in descriptors]
    manifest["array_bundle_hash"] = canonical_hash(
        {
            "storage_profile": manifest["storage_profile"],
            "source_numerical_result_hash": operator.source_numerical_result_hash,
            "array_descriptors": manifest["array_descriptors"],
        }
    )
    manifest.pop("recovery_operator_hash")
    arrays = {row.name: operator.array(row.name) for row in operator.descriptors}
    arrays[name] = changed
    altered = replace(
        operator,
        descriptors=tuple(descriptors),
        array_bundle_hash=manifest["array_bundle_hash"],
        recovery_operator_hash=canonical_hash(manifest),
        _arrays=MappingProxyType(arrays),
    )
    assert validate_fiber_frame_nonlinear_recovery_operator_shape(altered) is altered
    return altered


@pytest.mark.parametrize("entry", ("validate_operator", "create_with_operator"))
def test_rehashed_one_ulp_array_is_rejected_by_independent_engineering_replay(
    recovered, rehashed_one_ulp_operator, entry
) -> None:
    with pytest.raises(
        FiberFrameNonlinearRecoveryError,
        match="fiber_frame_recovery_operator_replay_mismatch",
    ):
        _invoke_recovery_entry(entry, recovered, operator=rehashed_one_ulp_operator)


@pytest.mark.parametrize(
    "entry",
    (
        "create_operator",
        "create_engineering",
        "operator_manifest",
        "engineering_manifest",
    ),
)
def test_prior_validation_does_not_hide_later_mutation_of_an_early_source_step(
    recovered, entry
) -> None:
    _invoke_recovery_entry(entry, recovered)
    path = recovered["path"]
    # Frozen outer records retain mutable Newton dictionaries, including aliases
    # returned by to_dict(). Mutate an early epoch, leaving terminal output alone.
    metrics = path.to_dict()["steps"][0]["trial_solution"]["metrics"]
    assert metrics is path.steps[0].trial_solution.metrics
    saved = deepcopy(metrics)
    try:
        metrics["relative_residual"] = float(metrics["relative_residual"]) + 1.0
        with pytest.raises(
            FiberFrameNonlinearTerminalReceiptError,
            match="source_path_replay_mismatch",
        ):
            _invoke_recovery_entry(entry, recovered)
    finally:
        metrics.clear()
        metrics.update(saved)


@pytest.mark.parametrize("entry", ("create_operator", "create_engineering"))
def test_invalid_adapter_is_rejected_before_engineering_replay(
    recovered, monkeypatch, entry
) -> None:
    adapter = replace(recovered["adapter"], adapter_hash=_hash("f"))

    def forbidden_replay(_adapter):
        pytest.fail("an invalid adapter must not reach engineering replay")

    monkeypatch.setattr(
        recovery_module, "_replay_terminal_engineering_outputs", forbidden_replay
    )
    with pytest.raises(
        FiberFrameNonlinearResultAdapterError,
        match="fiber_frame_result_adapter_hash_mismatch",
    ):
        _invoke_recovery_entry(entry, recovered, adapter=adapter)


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
