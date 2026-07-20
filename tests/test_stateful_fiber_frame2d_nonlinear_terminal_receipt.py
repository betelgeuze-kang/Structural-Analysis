from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from structural_analysis.assembly import (
    make_stateful_fiber_frame2d_checkpoint_chain,
    run_stateful_fiber_frame2d_load_path,
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
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    create_fiber_frame_nonlinear_execution_state_binding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    FIBER_FRAME_NONLINEAR_TERMINAL_AUTHORITY_PROFILE,
    FIBER_FRAME_NONLINEAR_TERMINAL_CLAIM_BOUNDARY,
    FiberFrameNonlinearTerminalReceiptError,
    _step_payload,
    _terminal_payload,
    create_fiber_frame_nonlinear_terminal_receipt,
    validate_fiber_frame_nonlinear_terminal_receipt,
    validate_fiber_frame_nonlinear_terminal_receipt_manifest,
    validate_fiber_frame_nonlinear_terminal_receipt_shape,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
)
from structural_analysis.benchmark import make_two_member_stateful_fiber_l_frame
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64
NODE_IDS = ("N1", "N2", "N3")
LOAD_FACTORS = (0.25, 0.5, 0.75, 1.0)


def _artifacts():
    problem = make_two_member_stateful_fiber_l_frame()
    path = run_stateful_fiber_frame2d_load_path(
        problem,
        LOAD_FACTORS,
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    checkpoint_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        (
            path.initial_checkpoint,
            *(step.accepted_checkpoint for step in path.steps),
        ),
    )
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    scaling = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
    )
    material = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hashes=kinematic.solver_state_hashes,
    )
    binding = create_fiber_frame_nonlinear_execution_state_binding(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
    )
    receipt = create_fiber_frame_nonlinear_terminal_receipt(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
        binding,
        path,
    )
    return (
        problem,
        path,
        checkpoint_chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
        receipt,
    )


@pytest.fixture(scope="module")
def artifacts():
    return _artifacts()


def _rehash_step(row):
    provisional = replace(row, step_receipt_hash="sha256:" + "0" * 64)
    return replace(
        provisional,
        step_receipt_hash=canonical_hash(
            _step_payload(provisional, include_step_receipt_hash=False)
        ),
    )


def _rehash_terminal(receipt):
    step_chain_hash = canonical_hash(
        {
            "root_checkpoint_state_hash": receipt.root_checkpoint_state_hash,
            "step_receipt_hashes": [
                row.step_receipt_hash for row in receipt.step_receipts
            ],
        }
    )
    audit_chain_hash = canonical_hash(
        {
            "jacobian_audit_hashes": [
                row.jacobian_audit.audit_hash for row in receipt.step_receipts
            ]
        }
    )
    provisional = replace(
        receipt,
        terminal_receipt_hash="sha256:" + "0" * 64,
        step_receipt_chain_hash=step_chain_hash,
        jacobian_audit_chain_hash=audit_chain_hash,
    )
    return replace(
        provisional,
        terminal_receipt_hash=canonical_hash(
            _terminal_payload(provisional, include_terminal_receipt_hash=False)
        ),
    )


def test_terminal_receipt_binds_exact_j4_full_load_path(artifacts) -> None:
    (
        problem,
        path,
        checkpoint_chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
        receipt,
    ) = artifacts

    assert receipt.authority_profile == FIBER_FRAME_NONLINEAR_TERMINAL_AUTHORITY_PROFILE
    assert receipt.execution_state_binding_hash == binding.binding_hash
    assert receipt.execution_topology_plan_hash == plan.plan_hash
    assert receipt.execution_operator_hash == plan.operator_hash
    assert receipt.execution_numeric_buffer_hash == plan.numeric_buffer_hash
    assert receipt.physical_equation_scaling_binding_hash == scaling.binding_hash
    assert receipt.engine_equation_scaling_hash == scaling.engine_equation_scaling_hash
    assert receipt.checkpoint_chain_hash == checkpoint_chain.chain_hash
    assert receipt.kinematic_state_chain_hash == kinematic.chain_hash
    assert receipt.material_state_projection_chain_hash == material.chain_hash
    assert receipt.problem_contract_hash == problem.contract_hash
    assert receipt.accepted_step_count == len(path.steps) == 4
    assert receipt.terminal_epoch == path.final_checkpoint.epoch == 4
    assert receipt.terminal_load_factor == 1.0
    assert receipt.converged is True
    assert receipt.fallback_count == receipt.regularization_count == 0
    assert (
        tuple(row.target_load_factor for row in receipt.step_receipts) == LOAD_FACTORS
    )
    assert receipt.terminal_checkpoint_state_hash == path.final_checkpoint.state_hash
    assert (
        receipt.terminal_checkpoint_state_hash == binding.terminal_checkpoint_state_hash
    )
    assert (
        receipt.terminal_kinematic_state_hash == binding.terminal_kinematic_state_hash
    )
    assert (
        receipt.terminal_material_state_bundle_hash
        == binding.terminal_material_state_bundle_hash
    )


def test_every_step_replays_physical_residual_and_same_parent_jacobian(
    artifacts,
) -> None:
    *_, binding, receipt = artifacts

    for index, row in enumerate(receipt.step_receipts, start=1):
        epoch = binding.epoch_bindings[index]
        assert row.epoch == row.step_index == index
        assert row.accepted_checkpoint_state_hash == epoch.checkpoint_state_hash
        assert row.committed_kinematic_state_hash == (
            epoch.committed_kinematic_state_hash
        )
        assert row.committed_material_state_bundle_hash == (
            epoch.committed_material_state_bundle_hash
        )
        assert row.residual_gate_passed is True
        assert row.increment_gate_passed is True
        assert row.convergence_gate_passed is True
        assert row.scaled_residual_linf <= row.scaled_residual_tolerance
        assert (
            row.solver_coordinate_increment_linf_m
            <= row.solver_coordinate_increment_tolerance_m
        )
        assert row.jacobian_audit.passed is True
        assert row.jacobian_audit.same_committed_parent_checkpoint is True
        assert row.jacobian_audit.parent_checkpoint_state_hash == (
            row.parent_checkpoint_state_hash
        )
        assert row.jacobian_audit.relative_inf_error <= (
            row.jacobian_audit.relative_tolerance
        )


def test_dimensional_and_dimensionless_norms_remain_distinct(artifacts) -> None:
    *_, scaling, _, _, _, receipt = artifacts
    final = receipt.step_receipts[-1]

    expected_scaled_linf = max(
        final.raw_translation_linf_n / scaling.reference_force_n,
        final.raw_rotation_linf_nm
        / (scaling.reference_force_n * scaling.characteristic_length_m),
    )
    assert final.raw_translation_linf_n >= 0.0
    assert final.raw_rotation_linf_nm >= 0.0
    assert final.scaled_residual_linf == pytest.approx(expected_scaled_linf)
    assert final.raw_translation_linf_n != final.scaled_residual_linf
    assert final.raw_rotation_linf_nm != final.scaled_residual_linf
    assert final.dimensionless_increment_linf >= 0.0
    assert final.dimensionless_increment_tolerance > 0.0


def test_manifest_retains_binary_identities_without_json_vectors(artifacts) -> None:
    *_, receipt = artifacts
    manifest = receipt.to_manifest()

    assert (
        validate_fiber_frame_nonlinear_terminal_receipt_manifest(manifest) == manifest
    )
    assert manifest["claim_boundary"] == dict(
        FIBER_FRAME_NONLINEAR_TERMINAL_CLAIM_BOUNDARY
    )
    assert manifest["claim_boundary"]["bounded_path_convergence_authority"] is True
    assert manifest["claim_boundary"]["manifest_only_source_replay_authority"] is False
    assert manifest["claim_boundary"]["nonlinear_numerical_result_authority"] is False
    assert manifest["claim_boundary"]["g1_closure"] is False
    for row in manifest["step_receipts"]:
        assert row["binary_identities"]["storage_profile"] == (
            "canonical_little_endian_float64_hash_only.v1"
        )
        assert "free_displacements_m" not in row
        assert "residual_kn" not in row
        assert "convergence_history" not in row
        assert "line_search_history" not in row
        assert "vectors" not in row
        assert row["jacobian_audit"]["binary_identities"]["storage_profile"] == (
            "canonical_little_endian_float64_hash_only.v1"
        )


def test_full_validator_replays_all_sources(artifacts) -> None:
    (
        problem,
        path,
        checkpoint_chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
        receipt,
    ) = artifacts

    assert (
        validate_fiber_frame_nonlinear_terminal_receipt(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            material,
            binding,
            path,
            receipt,
        )
        is receipt
    )


def test_repeated_creation_is_hash_identical(artifacts) -> None:
    (
        problem,
        path,
        checkpoint_chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
        receipt,
    ) = artifacts

    repeated = create_fiber_frame_nonlinear_terminal_receipt(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
        binding,
        path,
    )
    assert repeated == receipt
    assert repeated.to_manifest() == receipt.to_manifest()


def test_sub_full_path_cannot_mint_terminal_receipt(artifacts) -> None:
    problem, _, checkpoint_chain, plan, scaling, kinematic, material, binding, _ = (
        artifacts
    )
    sub_full = run_stateful_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5),
        config=NewtonRaphsonConfig(max_iterations=40),
    )

    with pytest.raises(FiberFrameNonlinearTerminalReceiptError) as error:
        create_fiber_frame_nonlinear_terminal_receipt(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            material,
            binding,
            sub_full,
        )
    assert error.value.code in {
        "fiber_frame_nonlinear_terminal_source_path_count_invalid",
        "fiber_frame_nonlinear_terminal_source_path_checkpoint_mismatch",
    }


def test_blocked_step_cannot_mint_terminal_receipt(artifacts) -> None:
    problem, _, checkpoint_chain, plan, scaling, kinematic, material, binding, _ = (
        artifacts
    )
    blocked = run_stateful_fiber_frame2d_load_path(
        problem,
        (1.0,),
        config=NewtonRaphsonConfig(max_iterations=0),
    )

    with pytest.raises(FiberFrameNonlinearTerminalReceiptError):
        create_fiber_frame_nonlinear_terminal_receipt(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            material,
            binding,
            blocked,
        )


def test_coherently_rehashed_scalar_tamper_needs_full_source_replay(
    artifacts,
) -> None:
    (
        problem,
        path,
        checkpoint_chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
        receipt,
    ) = artifacts
    rows = list(receipt.step_receipts)
    rows[-1] = _rehash_step(replace(rows[-1], raw_translation_linf_n=0.0))
    tampered = _rehash_terminal(
        replace(
            receipt,
            step_receipts=tuple(rows),
            final_raw_translation_linf_n=0.0,
        )
    )

    validate_fiber_frame_nonlinear_terminal_receipt_shape(tampered)
    validate_fiber_frame_nonlinear_terminal_receipt_manifest(tampered.to_manifest())
    with pytest.raises(FiberFrameNonlinearTerminalReceiptError) as error:
        validate_fiber_frame_nonlinear_terminal_receipt(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            material,
            binding,
            path,
            tampered,
        )
    assert error.value.code == (
        "fiber_frame_nonlinear_terminal_receipt_source_replay_mismatch"
    )


def test_source_solution_metric_tamper_is_rejected_before_receipt_creation(
    artifacts,
) -> None:
    (
        problem,
        path,
        checkpoint_chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
        _,
    ) = artifacts
    steps = list(path.steps)
    final = steps[-1]
    metrics = deepcopy(final.trial_solution.metrics)
    metrics["relative_residual"] = metrics["relative_residual"] * 2.0
    steps[-1] = replace(
        final,
        trial_solution=replace(final.trial_solution, metrics=metrics),
    )
    tampered_path = replace(path, steps=tuple(steps))

    with pytest.raises(FiberFrameNonlinearTerminalReceiptError) as error:
        create_fiber_frame_nonlinear_terminal_receipt(
            problem,
            plan,
            scaling,
            checkpoint_chain,
            kinematic,
            material,
            binding,
            tampered_path,
        )
    assert error.value.code == (
        "fiber_frame_nonlinear_terminal_source_path_replay_mismatch"
    )


def test_manifest_rejects_unknown_fields_and_authority_promotion(artifacts) -> None:
    *_, receipt = artifacts
    unknown = deepcopy(receipt.to_manifest())
    unknown["unexpected"] = True
    with pytest.raises(FiberFrameNonlinearTerminalReceiptError):
        validate_fiber_frame_nonlinear_terminal_receipt_manifest(unknown)

    promoted = deepcopy(receipt.to_manifest())
    promoted["claim_boundary"]["nonlinear_numerical_result_authority"] = True
    unsigned = dict(promoted)
    unsigned.pop("terminal_receipt_hash")
    promoted["terminal_receipt_hash"] = canonical_hash(unsigned)
    with pytest.raises(FiberFrameNonlinearTerminalReceiptError) as error:
        validate_fiber_frame_nonlinear_terminal_receipt_manifest(promoted)
    assert error.value.code == "fiber_frame_nonlinear_terminal_claim_boundary_invalid"


def test_manifest_rejects_nonconverged_terminal_even_after_rehash(artifacts) -> None:
    *_, receipt = artifacts
    manifest = deepcopy(receipt.to_manifest())
    manifest["terminal"]["converged"] = False
    unsigned = dict(manifest)
    unsigned.pop("terminal_receipt_hash")
    manifest["terminal_receipt_hash"] = canonical_hash(unsigned)

    with pytest.raises(FiberFrameNonlinearTerminalReceiptError) as error:
        validate_fiber_frame_nonlinear_terminal_receipt_manifest(manifest)
    assert (
        error.value.code == "fiber_frame_nonlinear_terminal_receipt_convergence_invalid"
    )
