from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.ai import gate as gate_module  # noqa: E402
from structural_analysis.engine_v2.ai import shadow as shadow_module  # noqa: E402
from structural_analysis.engine_v2.ai.gate import (  # noqa: E402
    AIProposalGateError,
    evaluate_ai_proposal_gate,
    validate_ai_proposal_gate_receipt,
)
from structural_analysis.engine_v2.ai.projection import (  # noqa: E402
    build_fixed_rank_projection,
)
from structural_analysis.engine_v2.ai.proposal import (  # noqa: E402
    build_phase0_ai_proposal,
)
from structural_analysis.engine_v2.ai.shadow import (  # noqa: E402
    AIShadowRunError,
    run_ai_shadow_v1,
    validate_ai_shadow_run,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    compile_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = (
    SRC_ROOT
    / "structural_analysis/schemas/ai_proposal_gate_receipt_v1.schema.json"
)


def _artifacts(
    *,
    load_pattern_id: str = "LC_WEAK",
    coefficient_scale: float = 1.0,
):
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )
    plan = compile_execution_plan(buffers)
    accepted = create_initial_state(plan)
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    stiffness_ff = plan.operator.stiffness_matrix[np.ix_(free, free)]
    solution_free = np.linalg.solve(stiffness_ff, plan.operator.load_vector[free])
    projection = build_fixed_rank_projection(
        plan,
        solution_free.reshape((-1, 1)),
        rank_cap=1,
    )
    solution_scaled = solution_free / projection.scaling_diagonal
    exact_y = projection.basis_q.T @ solution_scaled
    coefficients = coefficient_scale * exact_y
    trust_radius = max(1.0e-12, float(np.linalg.norm(coefficients)) * 1.01)
    proposal = build_phase0_ai_proposal(
        plan,
        accepted,
        projection,
        coefficients,
        trust_radius,
    )
    return buffers, plan, accepted, projection, proposal


def _rehash_gate(receipt):
    provisional = replace(
        receipt,
        gate_receipt_hash="sha256:" + ("0" * 64),
    )
    return replace(
        provisional,
        gate_receipt_hash=gate_module._gate_receipt_hash(provisional),
    )


def _rehash_shadow(shadow):
    provisional = replace(
        shadow,
        shadow_run_hash="sha256:" + ("0" * 64),
    )
    return replace(
        provisional,
        shadow_run_hash=shadow_module._shadow_hash(provisional),
    )


def test_gate_schema_and_full_physics_replay_are_strict() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    _, plan, accepted, _, proposal = _artifacts()

    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    manifest = receipt.to_dict()

    assert not list(validator.iter_errors(manifest))
    assert receipt.status == "rejected"
    assert receipt.reason_codes == (
        "ood_not_evaluated",
        "statistical_calibration_missing",
    )
    assert receipt.checks.full_residual_replayed is True
    assert receipt.checks.free_scaled_residual_reduced is True
    assert receipt.checks.total_potential_energy_nonincrease is True
    assert receipt.checks.constrained_increment_exact_zero is True
    assert receipt.checks.stateless_linear_elastic_constitutive_replayed is True
    assert receipt.checks.constitutive_admissibility_pass is True
    assert receipt.checks.ood_policy_pass is False
    assert receipt.checks.eligible_initial_guess is False
    assert receipt.physics_replay.scaled_residual_definition == (
        "l2_of_D_times_free_residual_D_equals_inv_sqrt_diag_Kff"
    )
    assert receipt.physics_replay.constitutive_mode == "stateless_linear_elastic"
    assert receipt.proposal_policy.trust_coordinate_units == (
        "sqrt_joule_energy_coordinate"
    )
    assert receipt.physics_replay.trial_scaled_free_residual < 1.0e-12
    assert receipt.physics_replay.trial_total_potential_energy_j <= (
        receipt.physics_replay.base_total_potential_energy_j
    )
    assert receipt.physics_replay.constitutive_operator_consistency_linf <= (
        receipt.physics_replay.constitutive_force_tolerance
    )
    assert receipt.physics_replay.constitutive_energy_consistency_abs_j <= (
        receipt.physics_replay.constitutive_energy_tolerance_j
    )
    assert receipt.authority.eligible_use == "initial_guess_only"
    assert receipt.authority.commit_performed is False
    assert receipt.authority.final_result is False
    assert receipt.authority.authoritative_result is False
    assert receipt.authority.speed_claim_allowed is False
    validate_ai_proposal_gate_receipt(
        receipt,
        expected_plan=plan,
        expected_accepted_state=accepted,
        expected_proposal=proposal,
    )

    with_extra = receipt.to_dict()
    with_extra["authority"]["commit_state_hash"] = accepted.state_hash
    assert list(validator.iter_errors(with_extra))


def test_gate_allows_rank_cap_larger_than_free_space_when_retained_rank_fits() -> None:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE),
        load_pattern_id="LC_WEAK",
    )
    plan = compile_execution_plan(buffers)
    accepted = create_initial_state(plan)
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    stiffness_ff = plan.operator.stiffness_matrix[np.ix_(free, free)]
    solution_free = np.linalg.solve(
        stiffness_ff,
        plan.operator.load_vector[free],
    )
    projection = build_fixed_rank_projection(
        plan,
        solution_free.reshape((-1, 1)),
    )
    coefficients = projection.basis_q.T @ (
        solution_free / projection.scaling_diagonal
    )
    proposal = build_phase0_ai_proposal(
        plan,
        accepted,
        projection,
        coefficients,
        max(1.0e-12, float(np.linalg.norm(coefficients)) * 1.01),
    )

    assert proposal.rank_cap == 16
    assert proposal.free_dof_count < proposal.rank_cap
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    assert receipt.checks.rank_budget_pass is True
    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)
    validate_ai_shadow_run(shadow)


def test_gate_trust_boundary_matches_proposal_64_ulp_tolerance() -> None:
    _, plan, accepted, projection, _ = _artifacts()
    boundary_coefficient = 1.0
    for _ in range(40):
        boundary_coefficient = float(
            np.nextafter(boundary_coefficient, np.inf)
        )
    proposal = build_phase0_ai_proposal(
        plan,
        accepted,
        projection,
        np.asarray([boundary_coefficient], dtype="<f8"),
        1.0,
    )

    assert proposal.coefficient_l2_norm > proposal.trust_radius
    assert proposal.coefficient_l2_norm <= (
        proposal.trust_radius + proposal.trust_absolute_tolerance
    )
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    assert receipt.checks.trust_budget_pass is True


def test_scaled_residual_uses_jacobi_energy_coordinates_not_load_scaling() -> None:
    _, plan, accepted, _, proposal = _artifacts(coefficient_scale=0.5)
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    diagonal = plan.operator.stiffness_matrix[free, free]
    jacobi_d = 1.0 / np.sqrt(diagonal)
    base_r = (
        plan.operator.stiffness_matrix @ accepted.displacement_si
        - plan.operator.load_vector
    )
    correction = proposal.array("correction_free")
    trial_u = np.array(accepted.displacement_si, copy=True)
    trial_u[free] += correction
    trial_r = plan.operator.stiffness_matrix @ trial_u - plan.operator.load_vector

    assert receipt.physics_replay.base_scaled_free_residual == pytest.approx(
        np.linalg.norm(jacobi_d * base_r[free]), rel=1.0e-15
    )
    assert receipt.physics_replay.trial_scaled_free_residual == pytest.approx(
        np.linalg.norm(jacobi_d * trial_r[free]), rel=1.0e-15
    )
    load_normalized_linf = np.max(np.abs(trial_r[free])) / max(
        1.0, np.max(np.abs(plan.operator.load_vector[free]))
    )
    assert receipt.physics_replay.trial_scaled_free_residual != pytest.approx(
        load_normalized_linf
    )


@pytest.mark.parametrize("coefficient_scale", [0.0, -1.0])
def test_gate_rejects_nonimproving_or_energy_increasing_correction(
    coefficient_scale: float,
) -> None:
    _, plan, accepted, _, proposal = _artifacts(
        coefficient_scale=coefficient_scale
    )
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)

    assert receipt.status == "rejected"
    assert "free_scaled_residual_not_reduced" in receipt.reason_codes
    if coefficient_scale < 0.0:
        assert "potential_energy_increased" in receipt.reason_codes
        assert receipt.checks.total_potential_energy_nonincrease is False
    assert receipt.rollback_proof.rollback_returned_exact_accepted_object is True
    assert receipt.rollback_proof.trial_committed is False
    assert receipt.rollback_proof.state_commit_count == 0


def test_gate_failure_path_rolls_back_and_preserves_exact_accepted_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, plan, accepted, _, proposal = _artifacts()
    before_hash = accepted.state_hash
    before_bytes = accepted.displacement_si.tobytes(order="C")
    rollback_calls = 0
    original_rollback = gate_module.rollback_trial_state

    def counted_rollback(*args, **kwargs):
        nonlocal rollback_calls
        rollback_calls += 1
        return original_rollback(*args, **kwargs)

    def failed_replay(*_args, **_kwargs):
        raise RuntimeError("injected replay failure")

    monkeypatch.setattr(gate_module, "rollback_trial_state", counted_rollback)
    monkeypatch.setattr(gate_module, "_authoritative_physics_replay", failed_replay)

    with pytest.raises(AIProposalGateError) as error:
        evaluate_ai_proposal_gate(plan, accepted, proposal)
    assert error.value.code == "gate_authoritative_replay_failed"
    assert rollback_calls == 1
    assert accepted.state_hash == before_hash
    assert accepted.displacement_si.tobytes(order="C") == before_bytes


def test_gate_receipt_hash_and_semantic_tampering_fail_closed() -> None:
    _, plan, accepted, _, proposal = _artifacts()
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    stale = replace(receipt, gate_receipt_hash="sha256:" + ("0" * 64))

    with pytest.raises(AIProposalGateError) as hash_error:
        validate_ai_proposal_gate_receipt(stale)
    assert hash_error.value.code == "gate_receipt_hash_mismatch"

    bad_replay = replace(
        receipt.physics_replay,
        scaled_free_residual_reduction=(
            receipt.physics_replay.scaled_free_residual_reduction + 1.0
        ),
    )
    forged = replace(
        receipt,
        physics_replay=bad_replay,
        gate_receipt_hash="sha256:" + ("0" * 64),
    )
    forged = replace(
        forged,
        gate_receipt_hash=gate_module._gate_receipt_hash(forged),
    )
    with pytest.raises(AIProposalGateError) as metric_error:
        validate_ai_proposal_gate_receipt(forged)
    assert metric_error.value.code == "gate_receipt_derived_metric_mismatch"

    bad_checks = replace(
        receipt.checks,
        stateless_linear_elastic_constitutive_replayed=False,
        constitutive_admissibility_pass=False,
    )
    semantic = replace(receipt, checks=bad_checks)
    semantic = replace(
        semantic,
        reason_codes=gate_module._reason_codes(
            semantic.proposal_policy, semantic.checks
        ),
        gate_receipt_hash="sha256:" + ("0" * 64),
    )
    semantic = replace(
        semantic,
        gate_receipt_hash=gate_module._gate_receipt_hash(semantic),
    )
    with pytest.raises(AIProposalGateError) as constitutive_error:
        validate_ai_proposal_gate_receipt(semantic)
    assert constitutive_error.value.code == (
        "gate_receipt_constitutive_check_mismatch"
    )


@pytest.mark.parametrize(
    "check_name",
    ["initial_guess_hook_pass", "trust_budget_pass"],
)
def test_gate_standalone_recomputes_rehashed_policy_checks(
    check_name: str,
) -> None:
    _, plan, accepted, _, proposal = _artifacts()
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    bad_checks = replace(receipt.checks, **{check_name: False})
    forged = replace(
        receipt,
        checks=bad_checks,
        reason_codes=gate_module._reason_codes(
            receipt.proposal_policy,
            bad_checks,
        ),
    )
    forged = _rehash_gate(forged)

    with pytest.raises(AIProposalGateError) as error:
        validate_ai_proposal_gate_receipt(forged)
    assert error.value.code == "gate_receipt_policy_check_mismatch"


def test_gate_standalone_rejects_rehashed_nondeterministic_gate_id() -> None:
    _, plan, accepted, _, proposal = _artifacts()
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    forged = _rehash_gate(replace(receipt, gate_id="Gate:forged"))

    with pytest.raises(AIProposalGateError) as error:
        validate_ai_proposal_gate_receipt(forged)
    assert error.value.code == "gate_receipt_id_mismatch"


def test_gate_v1_rejects_detached_rehashed_calibration_promotion() -> None:
    _, plan, accepted, _, proposal = _artifacts()
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    promoted_policy = replace(
        receipt.proposal_policy,
        ood_status="in_distribution",
        statistical_calibration=True,
    )
    promoted_checks = replace(
        receipt.checks,
        ood_policy_pass=True,
        eligible_initial_guess=True,
    )
    forged = _rehash_gate(
        replace(
            receipt,
            status="eligible_initial_guess",
            reason_codes=("eligible_initial_guess",),
            proposal_policy=promoted_policy,
            checks=promoted_checks,
        )
    )

    with pytest.raises(AIProposalGateError) as error:
        validate_ai_proposal_gate_receipt(forged)
    assert error.value.code == "gate_receipt_schema_invalid"


@pytest.mark.parametrize(
    ("hash_kind", "fake_hash"),
    [
        ("state", "sha256:" + ("a" * 64)),
        ("displacement", "sha256:" + ("b" * 64)),
    ],
)
def test_gate_standalone_binds_rehashed_rollback_to_input(
    hash_kind: str,
    fake_hash: str,
) -> None:
    _, plan, accepted, _, proposal = _artifacts()
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    if hash_kind == "state":
        rollback = replace(
            receipt.rollback_proof,
            accepted_state_hash_before=fake_hash,
            accepted_state_hash_after=fake_hash,
        )
    else:
        rollback = replace(
            receipt.rollback_proof,
            accepted_displacement_hash_before=fake_hash,
            accepted_displacement_hash_after=fake_hash,
        )
    forged = _rehash_gate(replace(receipt, rollback_proof=rollback))

    with pytest.raises(AIProposalGateError) as error:
        validate_ai_proposal_gate_receipt(forged)
    assert error.value.code == "gate_receipt_rollback_binding_mismatch"


def test_gate_standalone_rejects_impossible_full_vs_free_residual() -> None:
    _, plan, accepted, _, proposal = _artifacts()
    receipt = evaluate_ai_proposal_gate(plan, accepted, proposal)
    bad_replay = replace(
        receipt.physics_replay,
        base_full_residual_linf=0.0,
    )
    forged = _rehash_gate(replace(receipt, physics_replay=bad_replay))

    with pytest.raises(AIProposalGateError) as error:
        validate_ai_proposal_gate_receipt(forged)
    assert error.value.code == "gate_receipt_residual_subset_invalid"


def test_shadow_runs_gate_first_then_authoritative_solver_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffers, plan, accepted, _, proposal = _artifacts()
    events: list[str] = []
    original_gate = shadow_module.evaluate_ai_proposal_gate
    original_execute = shadow_module.execute_linear_static_plan_v1

    def recorded_gate(*args, **kwargs):
        events.append("gate")
        return original_gate(*args, **kwargs)

    def recorded_execute(*args, **kwargs):
        events.append("execute")
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(shadow_module, "evaluate_ai_proposal_gate", recorded_gate)
    monkeypatch.setattr(
        shadow_module, "execute_linear_static_plan_v1", recorded_execute
    )
    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)

    assert events == ["gate", "execute", "execute"]
    assert shadow.status == "shadow_verified"
    assert shadow.gate_receipt.status == "rejected"
    assert shadow.authoritative_solver_invocation_count == 2
    assert shadow.proposal_consumed_by_authoritative_solver is False
    assert shadow.direct_solver_initial_guess_supported is False
    assert shadow.commit_performed_by_ai is False
    assert shadow.speed_claim_allowed is False
    assert shadow.timing_measured is False
    assert shadow.parity.input_and_plan_bindings_bit_identical is True
    assert shadow.parity.all_authoritative_outputs_bit_identical is True
    assert shadow.ai_off_run.backend_result.result_hash == (
        shadow.ai_on_run.backend_result.result_hash
    )
    assert shadow.ai_off_run.result_ir.result_ir_hash == (
        shadow.ai_on_run.result_ir.result_ir_hash
    )
    assert shadow.ai_off_run.receipt_chain_hash == (
        shadow.ai_on_run.receipt_chain_hash
    )
    validate_ai_shadow_run(
        shadow,
        expected_buffers=buffers,
        expected_plan=plan,
        expected_accepted_state=accepted,
        expected_proposal=proposal,
    )


def test_shadow_standalone_validation_rejects_cross_plan_splicing() -> None:
    buffers_a, plan_a, accepted_a, _, proposal_a = _artifacts(
        load_pattern_id="LC_WEAK"
    )
    buffers_b, plan_b, accepted_b, _, proposal_b = _artifacts(
        load_pattern_id="LC_STRONG"
    )
    shadow_a = run_ai_shadow_v1(buffers_a, plan_a, accepted_a, proposal_a)
    shadow_b = run_ai_shadow_v1(buffers_b, plan_b, accepted_b, proposal_b)
    forged = replace(
        shadow_a,
        ai_off_run=shadow_b.ai_off_run,
        ai_on_run=shadow_b.ai_on_run,
        parity=shadow_b.parity,
        shadow_run_hash="sha256:" + ("0" * 64),
    )
    forged = replace(
        forged,
        shadow_run_hash=shadow_module._shadow_hash(forged),
    )

    with pytest.raises(AIShadowRunError) as error:
        validate_ai_shadow_run(forged)
    assert error.value.code == "ai_shadow_input_binding_mismatch"


def test_shadow_standalone_binds_gate_epoch_to_authoritative_initial_state() -> None:
    buffers, plan, accepted, _, proposal = _artifacts()
    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)
    bindings = replace(
        shadow.gate_receipt.input_bindings,
        accepted_state_epoch=(
            shadow.gate_receipt.input_bindings.accepted_state_epoch + 1
        ),
    )
    gate = _rehash_gate(
        replace(shadow.gate_receipt, input_bindings=bindings)
    )
    forged = _rehash_shadow(replace(shadow, gate_receipt=gate))

    with pytest.raises(AIShadowRunError) as error:
        validate_ai_shadow_run(forged)
    assert error.value.code == "ai_shadow_initial_state_epoch_mismatch"


def test_shadow_standalone_binds_policy_free_dofs_to_authoritative_plan() -> None:
    buffers, plan, accepted, _, proposal = _artifacts()
    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)
    policy = replace(
        shadow.gate_receipt.proposal_policy,
        free_dof_count=(
            shadow.gate_receipt.proposal_policy.free_dof_count + 1
        ),
    )
    gate = _rehash_gate(replace(shadow.gate_receipt, proposal_policy=policy))
    forged = _rehash_shadow(replace(shadow, gate_receipt=gate))

    with pytest.raises(AIShadowRunError) as error:
        validate_ai_shadow_run(forged)
    assert error.value.code == "ai_shadow_free_dof_count_mismatch"


def test_shadow_standalone_binds_gate_displacement_to_initial_state() -> None:
    buffers, plan, accepted, _, proposal = _artifacts()
    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)
    fake_hash = "sha256:" + ("c" * 64)
    bindings = replace(
        shadow.gate_receipt.input_bindings,
        accepted_displacement_hash=fake_hash,
    )
    rollback = replace(
        shadow.gate_receipt.rollback_proof,
        accepted_displacement_hash_before=fake_hash,
        accepted_displacement_hash_after=fake_hash,
    )
    gate = _rehash_gate(
        replace(
            shadow.gate_receipt,
            input_bindings=bindings,
            rollback_proof=rollback,
        )
    )
    forged = _rehash_shadow(replace(shadow, gate_receipt=gate))

    with pytest.raises(AIShadowRunError) as error:
        validate_ai_shadow_run(forged)
    assert error.value.code == (
        "ai_shadow_initial_displacement_binding_mismatch"
    )


def test_shadow_rejects_later_committed_base_until_warm_start_exists() -> None:
    buffers, plan, accepted, projection, proposal = _artifacts()
    trial_displacement = np.array(accepted.displacement_si, copy=True)
    trial_displacement[np.asarray(plan.free_dofs, dtype=np.int64)] += (
        proposal.correction_free
    )
    trial = open_trial_state(
        accepted,
        trial_displacement,
        expected_plan=plan,
    )
    later_committed = commit_trial_state(
        accepted,
        trial,
        expected_plan=plan,
    )
    later_proposal = build_phase0_ai_proposal(
        plan,
        later_committed,
        projection,
        np.zeros(projection.retained_rank, dtype="<f8"),
        1.0,
    )

    with pytest.raises(AIShadowRunError) as error:
        run_ai_shadow_v1(
            buffers,
            plan,
            later_committed,
            later_proposal,
        )
    assert error.value.code == "ai_shadow_non_initial_base_unsupported"


def test_shadow_hash_tampering_fails_closed() -> None:
    buffers, plan, accepted, _, proposal = _artifacts()
    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)
    stale = replace(shadow, shadow_run_hash="sha256:" + ("0" * 64))

    with pytest.raises(AIShadowRunError) as error:
        validate_ai_shadow_run(stale, expected_buffers=buffers)
    assert error.value.code == "ai_shadow_hash_mismatch"
